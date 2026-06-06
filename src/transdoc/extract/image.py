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


def _preprocess(img_bytes: bytes) -> bytes:
    """Deskew + denoise + grayscale to help OCR. No-op if OpenCV missing."""
    try:
        import cv2
        import numpy as np

        arr = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return img_bytes
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
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
                gray = cv2.warpAffine(gray, m, (w, h),
                                      flags=cv2.INTER_CUBIC,
                                      borderMode=cv2.BORDER_REPLICATE)
        gray = cv2.fastNlMeansDenoising(gray, h=10)
        ok, buf = cv2.imencode(".png", gray)
        return buf.tobytes() if ok else img_bytes
    except Exception:
        return img_bytes


def extract(path: str, cfg: Config) -> Document:
    raw = Path(path).read_bytes()
    pre = _preprocess(raw)
    ocr = get_ocr(cfg)
    out = Document(source_path=path, mime="image", page_count=1)
    out.blocks = ocr.recognize_image_bytes(pre, cfg, page=0)
    out.profile.input_nature = "photo/scan"
    reflow_order(out)
    return out
