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


def _avg_conf(blocks: list[Block]) -> float:
    cs = [b.confidence.ocr for b in blocks if b.confidence.ocr is not None]
    return sum(cs) / len(cs) if cs else 1.0


def run_with_escalation(engines: list, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
    """Run an ordered engine chain (primary first). Keep the primary if it's confident enough;
    otherwise retry the primary on a cleaned image, then escalate through the remaining engines,
    always keeping the most-confident pass. `engines` may contain None (unavailable) -> skipped."""
    engines = [e for e in engines if e is not None]
    if not engines:
        return []
    primary = engines[0]
    best = primary.recognize_image_bytes(img, cfg, page)
    best_c = _avg_conf(best)
    if best_c >= ESCALATE_BELOW:
        return best

    # 1) cheap retry on a cleaned image (grayscale/denoise/binarize, geometry-preserving):
    #    recovers noisy/low-contrast scans and dense form cells without a second engine.
    from .preprocess import enhance
    try:
        pre = enhance(img)
        if pre is not img:
            pblocks = primary.recognize_image_bytes(pre, cfg, page)
            if _avg_conf(pblocks) > best_c:
                best, best_c = pblocks, _avg_conf(pblocks)
    except Exception:
        pass
    if best_c >= ESCALATE_BELOW:
        return best

    # 2) escalate through the stronger engines; keep whichever pass is most confident.
    for eng in engines[1:]:
        try:
            alt = eng.recognize_image_bytes(img, cfg, page)
            if _avg_conf(alt) > best_c:
                best, best_c = alt, _avg_conf(alt)
                if best_c >= ESCALATE_BELOW:
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
