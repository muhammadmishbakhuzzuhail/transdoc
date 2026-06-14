"""AUTO OCR: Tesseract first (fast, always available); escalate only the low-confidence pages
to PaddleOCR when it's installed. This keeps clean pages cheap while recovering the degraded /
non-Latin scans where Tesseract collapses (see docs/RESEARCH.md), without paying PaddleOCR's
cost on every page.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block

# Below this average OCR confidence, a page is worth a second pass with a stronger engine.
ESCALATE_BELOW = 0.6


def _avg_conf(blocks: list[Block]) -> float:
    cs = [b.confidence.ocr for b in blocks if b.confidence.ocr is not None]
    return sum(cs) / len(cs) if cs else 1.0


class EscalatingOCR:
    name = "auto"

    def __init__(self):
        from .tesseract import TesseractOCR
        self._tess = TesseractOCR()
        self._strong = None          # lazily built PaddleOCR engine
        self._strong_tried = False

    def _get_strong(self):
        if not self._strong_tried:
            self._strong_tried = True
            try:
                import paddleocr  # noqa: F401
                from .paddle import PaddleOCREngine
                self._strong = PaddleOCREngine()
            except Exception:
                self._strong = None
        return self._strong

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        best = self._tess.recognize_image_bytes(img, cfg, page)
        best_c = _avg_conf(best)
        if best_c >= ESCALATE_BELOW:
            return best

        # 1) cheap retry on a cleaned image (grayscale/denoise/binarize, geometry-preserving):
        #    recovers noisy/low-contrast scans and dense form cells without a second engine.
        from .preprocess import enhance
        try:
            pre = enhance(img)
            if pre is not img:
                pblocks = self._tess.recognize_image_bytes(pre, cfg, page)
                if _avg_conf(pblocks) > best_c:
                    best, best_c = pblocks, _avg_conf(pblocks)
        except Exception:
            pass
        if best_c >= ESCALATE_BELOW:
            return best

        # 2) escalate to the stronger engine (PaddleOCR has its own preprocessing, so feed it
        #    the raw image). Keep whichever pass is most confident.
        strong = self._get_strong()
        if strong is None:
            return best
        try:
            better = strong.recognize_image_bytes(img, cfg, page)
            if _avg_conf(better) > best_c:
                best = better
        except Exception:
            pass
        return best
