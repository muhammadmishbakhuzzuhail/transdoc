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
        blocks = self._tess.recognize_image_bytes(img, cfg, page)
        if _avg_conf(blocks) >= ESCALATE_BELOW:
            return blocks
        strong = self._get_strong()
        if strong is None:
            return blocks            # nothing stronger available -> keep Tesseract's result
        try:
            better = strong.recognize_image_bytes(img, cfg, page)
        except Exception:
            return blocks
        # keep whichever pass is more confident (the stronger engine usually wins on the
        # hard pages, but not always — e.g. a blank/near-empty region)
        return better if _avg_conf(better) > _avg_conf(blocks) else blocks
