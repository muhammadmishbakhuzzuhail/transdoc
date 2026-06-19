# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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
    if choice == OCRChoice.EASYOCR:
        from .easyocr_engine import EasyOCREngine

        return EasyOCREngine()

    # AUTO: script-routed — detect each page's script, run the engine best for it, escalate the
    # low-confidence pages through the rest of that script's chain (router.py). With only Tesseract
    # installed every chain is tesseract(->paddle), i.e. the previous behavior.
    from .router import ScriptRoutedOCR

    return ScriptRoutedOCR()
