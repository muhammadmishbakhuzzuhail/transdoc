# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""OCR engine interface. Engines turn image bytes into IR blocks (text + bbox + conf)."""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..ir import Block


class OCREngine(Protocol):
    name: str

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        """Return IR blocks for one page image (PNG/JPEG bytes)."""
        ...


# Map ISO 639-1 (+ a few 639-3) -> tesseract codes. Install the matching tesseract-data-*
# pack for any language you OCR; missing packs just fall back to eng.
TESS_LANG = {
    "en": "eng", "id": "ind", "th": "tha", "vi": "vie", "ar": "ara", "zh": "chi_sim",
    "ja": "jpn", "ko": "kor", "ru": "rus", "hi": "hin", "de": "deu", "fr": "fra",
    "es": "spa", "pt": "por", "it": "ita", "nl": "nld",
    "el": "ell", "he": "heb", "iw": "heb", "bn": "ben", "la": "lat",
    "uk": "ukr", "fa": "fas", "ur": "urd", "ta": "tam", "te": "tel",
}
