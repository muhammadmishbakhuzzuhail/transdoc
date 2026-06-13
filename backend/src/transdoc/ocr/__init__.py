"""OCR engine factory. AUTO prefers Surya if importable (GPU), else Tesseract (CPU)."""

from __future__ import annotations

from ..config import Config, OCREngine as OCRChoice
from .base import OCREngine


def get_ocr(cfg: Config) -> OCREngine:
    choice = cfg.ocr_engine

    if choice == OCRChoice.SURYA:
        from .surya import SuryaOCR

        return SuryaOCR()
    if choice == OCRChoice.PADDLE:
        from .paddle import PaddleOCREngine

        return PaddleOCREngine()
    if choice == OCRChoice.TESSERACT:
        from .tesseract import TesseractOCR

        return TesseractOCR()

    # AUTO: Tesseract first, escalating low-confidence pages to PaddleOCR when installed
    # (fast common case, strong fallback on degraded/non-Latin scans).
    from .auto import EscalatingOCR

    return EscalatingOCR()
