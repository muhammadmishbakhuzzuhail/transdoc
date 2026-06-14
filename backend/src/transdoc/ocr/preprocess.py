"""Geometry-preserving image cleanup for OCR — a zero-extra-dependency CPU win for noisy /
low-contrast scans and dense form cells where Tesseract collapses.

Pillow only (already a dependency); NO OpenCV. Deliberately does NOT rotate, deskew, or
rescale: those move pixels, and the OCR bboxes must keep matching the source page geometry for
the in-place overlay / reconstruct renderers. We only adjust *intensity* — grayscale,
autocontrast, median denoise, Otsu binarization — which leaves every pixel coordinate where it
was, so the resulting bboxes drop straight back onto the original.

Used by the AUTO escalation path: a low-confidence page is retried on the cleaned image and the
higher-confidence result wins, so a clean page never pays for this and a bad clean-up can only
be discarded, never shipped.
"""

from __future__ import annotations


def _otsu_threshold(hist: list[int]) -> int:
    """Otsu's method: the histogram split that maximizes between-class variance."""
    total = sum(hist)
    if total == 0:
        return 127
    sum_all = sum(i * h for i, h in enumerate(hist))
    sum_b = 0.0
    w_b = 0
    best_var = -1.0
    thresh = 127
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best_var:
            best_var = between
            thresh = i
    return thresh


def enhance(img_bytes: bytes) -> bytes:
    """Grayscale -> autocontrast -> median denoise -> Otsu binarize. Same dimensions in/out
    (geometry preserved). Returns the original bytes unchanged if the image can't be read."""
    from io import BytesIO

    from PIL import Image, ImageFilter, ImageOps

    try:
        im = Image.open(BytesIO(img_bytes))
        im.load()
    except Exception:
        return img_bytes

    g = ImageOps.autocontrast(im.convert("L"))
    g = g.filter(ImageFilter.MedianFilter(3))            # kill speckle
    t = _otsu_threshold(g.histogram())
    bw = g.point(lambda p, t=t: 255 if p > t else 0, mode="L")
    out = BytesIO()
    bw.save(out, format="PNG")
    return out.getvalue()
