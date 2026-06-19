# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Image extraction: preprocess (deskew/denoise) -> OCR -> IR document.

Handles the "document is just a photo/scan" case. Preprocessing is best-effort and
skipped silently if OpenCV is unavailable.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..ir import Document
from ..ocr import get_ocr
from .base import reflow_order


def _coarse_orient(img_bytes: bytes) -> tuple[bytes, int]:
    """Correct a 90/180/270 page rotation via Tesseract OSD before OCR.

    Deskew (in _preprocess) only straightens a small tilt; a page photographed sideways or
    upside-down stays that way and OCR returns garbage (audit: a 90deg-rotated form extracted as
    vertical gibberish strips). OSD reports the coarse rotation; we rotate the image upright so
    the OCR — and the overlay background built from these bytes — are oriented correctly.

    Returns (possibly-rotated PNG bytes, degrees rotated clockwise). No-op (raw, 0) when OSD or
    Pillow/tesseract is unavailable or the page is already upright."""
    try:
        import io
        import re

        import pytesseract
        from PIL import Image

        im = Image.open(io.BytesIO(img_bytes))
        osd = pytesseract.image_to_osd(im)
        m = re.search(r"Rotate:\s*(\d+)", osd)
        rot = int(m.group(1)) % 360 if m else 0
        if rot == 0:
            return img_bytes, 0
        # OSD "Rotate: N" = degrees to turn the page CLOCKWISE to upright; PIL rotates CCW, so -rot.
        out = im.rotate(-rot, expand=True)
        buf = io.BytesIO()
        out.convert("RGB").save(buf, format="PNG")
        return buf.getvalue(), rot
    except Exception:
        return img_bytes, 0


def _preprocess(img_bytes: bytes) -> tuple[bytes, bytes | None]:
    """Deskew + denoise + grayscale to help OCR.

    Returns (ocr_bytes, display_bytes). Both are deskewed by the SAME rotation so the OCR
    bboxes line up with the display image; ocr_bytes is grayscale+denoised (best for OCR),
    display_bytes is the deskewed COLOR image used as the overlay background (None if no
    deskew happened — the original is fine as-is). No-op if OpenCV is missing.
    """
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return img_bytes, None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        display = None
        # deskew via min-area rect of foreground
        inv = cv2.bitwise_not(gray)
        thr = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thr > 0))
        if len(coords) > 100:
            angle = cv2.minAreaRect(coords)[-1]
            angle = -(90 + angle) if angle < -45 else -angle
            if abs(angle) > 0.3:
                h, w = gray.shape
                m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
                gray = cv2.warpAffine(gray, m, (w, h), flags=cv2.INTER_CUBIC,
                                      borderMode=cv2.BORDER_REPLICATE)
                # apply the same rotation to the color image -> straight display background
                color = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                                       borderMode=cv2.BORDER_REPLICATE)
                ok_c, buf_c = cv2.imencode(".png", color)
                display = buf_c.tobytes() if ok_c else None
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        ok, buf = cv2.imencode(".png", gray)
        return (buf.tobytes() if ok else img_bytes), display
    except Exception:
        return img_bytes, None


def extract(path: str, cfg: Config) -> Document:
    raw = Path(path).read_bytes()
    oriented, rot = _coarse_orient(raw)            # fix 90/180/270 before fine deskew + OCR
    ocr_bytes, deskew_display = _preprocess(oriented)  # resilient: falls back to raw on bad image
    ocr = get_ocr(cfg)
    out = Document(source_path=path, mime="image", page_count=1)
    out.blocks = ocr.recognize_image_bytes(ocr_bytes, cfg, page=0)
    out.profile.input_nature = "photo/scan"
    # Overlay must sit on the SAME pixels the bboxes came from: prefer the deskewed copy, else the
    # coarse-oriented copy (when only rotation was applied), else the original needs no background.
    display_bytes = deskew_display or (oriented if rot else None)
    if display_bytes:
        import tempfile

        f = tempfile.NamedTemporaryFile(prefix="transdoc_disp_", suffix=".png", delete=False)
        f.write(display_bytes)
        f.close()
        out.render_path = f.name
    reflow_order(out)
    return out
