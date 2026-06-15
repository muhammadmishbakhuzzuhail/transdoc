"""Confidence escalation primitive shared by the OCR router.

`run_with_escalation` runs an ordered list of engines: the primary first, a cheap cleaned-image
retry on it, then each remaining (stronger) engine, always keeping the most-confident result.
`EscalatingOCR` is the original Tesseract->strong wrapper, kept for direct use + its tests; the
script-aware router (router.py) reuses the same primitive with a per-script engine chain.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block

# Below this average OCR confidence, a page is worth a second pass with a stronger engine.
ESCALATE_BELOW = 0.6
# Also escalate when this fraction of blocks is below the floor — a page can average "fine" yet
# leave many weak lines (e.g. Tesseract on a non-Latin scan: most lines ok, a chunk garbled). A
# stronger engine usually fixes the whole page, so don't settle for a good average with bad tails.
LOW_FRACTION = 0.25


def _avg_conf(blocks: list[Block]) -> float:
    cs = [b.confidence.ocr for b in blocks if b.confidence.ocr is not None]
    return sum(cs) / len(cs) if cs else 1.0


def _low_fraction(blocks: list[Block]) -> float:
    cs = [b.confidence.ocr for b in blocks if b.confidence.ocr is not None]
    return sum(1 for c in cs if c < ESCALATE_BELOW) / len(cs) if cs else 0.0


def _needs_escalation(blocks: list[Block]) -> bool:
    return _avg_conf(blocks) < ESCALATE_BELOW or _low_fraction(blocks) > LOW_FRACTION


def _quality(blocks: list[Block]) -> float:
    """Rank a pass: high average, few weak lines. Lets a stronger engine win even when its average
    is close, as long as it leaves fewer garbled lines."""
    return _avg_conf(blocks) - 0.3 * _low_fraction(blocks)


def run_with_escalation(engines: list, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
    """Run an ordered engine chain (primary first). Keep the primary if it's confident enough
    (good average AND few weak lines); otherwise retry the primary on a cleaned image, then
    escalate through the remaining engines, keeping the highest-quality pass. `engines` may
    contain None (unavailable) -> skipped."""
    engines = [e for e in engines if e is not None]
    if not engines:
        return []
    primary = engines[0]
    best = primary.recognize_image_bytes(img, cfg, page)
    if not _needs_escalation(best):
        return best

    # 1) cheap retry on a cleaned image (grayscale/denoise/binarize, geometry-preserving):
    #    recovers noisy/low-contrast scans and dense form cells without a second engine.
    from .preprocess import enhance
    try:
        pre = enhance(img)
        if pre is not img:
            pblocks = primary.recognize_image_bytes(pre, cfg, page)
            if _quality(pblocks) > _quality(best):
                best = pblocks
    except Exception:
        pass
    if not _needs_escalation(best):
        return best

    # 2) escalate through the stronger engines; keep whichever pass is highest quality.
    for eng in engines[1:]:
        try:
            alt = eng.recognize_image_bytes(img, cfg, page)
            if _quality(alt) > _quality(best):
                best = alt
                if not _needs_escalation(best):
                    break
        except Exception:
            continue
    return best


class EscalatingOCR:
    """Tesseract primary, escalating low-confidence pages to PaddleOCR when installed. Kept for
    direct use and its unit tests; the AUTO factory now returns the script-aware router."""

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
        return run_with_escalation([self._tess, self._get_strong()], img, cfg, page)
