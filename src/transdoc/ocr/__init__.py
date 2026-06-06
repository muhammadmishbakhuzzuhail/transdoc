"""OCR engine factory. AUTO prefers Surya if importable (GPU), else Tesseract (CPU)."""

from __future__ import annotations

from ..config import Config, OCREngine as OCRChoice
from .base import OCREngine


def get_ocr(cfg: Config) -> OCREngine:
    choice = cfg.ocr_engine

    if choice == OCRChoice.SURYA:
        from .surya import SuryaOCR

        return SuryaOCR()
    if choice == OCRChoice.TESSERACT:
        from .tesseract import TesseractOCR

        return TesseractOCR()

    # AUTO: try Surya, fall back to Tesseract.
    try:
        import surya  # noqa: F401

        from .surya import SuryaOCR

        return SuryaOCR()
    except Exception:
        from .tesseract import TesseractOCR

        return TesseractOCR()
