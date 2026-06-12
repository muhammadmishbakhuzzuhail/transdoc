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

    # AUTO: prefer PaddleOCR if installed (stronger, CPU-capable), else Surya (GPU), else
    # Tesseract (always available).
    try:
        import paddleocr  # noqa: F401

        from .paddle import PaddleOCREngine

        return PaddleOCREngine()
    except Exception:
        pass
    try:
        import surya  # noqa: F401

        from .surya import SuryaOCR

        return SuryaOCR()
    except Exception:
        from .tesseract import TesseractOCR

        return TesseractOCR()
