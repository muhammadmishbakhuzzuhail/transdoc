"""Script-routed OCR.

No single OCR wins every script, so route each page to the engine that's best for its writing
system, and escalate to the others when confidence is low — "if one language is weak in one OCR,
another covers it". Three pieces:

  1. detect_script(img)  - Tesseract OSD tells us the script (Latin/Arabic/Han/Devanagari/...).
  2. ROUTING / REGISTRY  - script -> ordered engine chain; engines built lazily, skipped if the
                           dependency isn't installed.
  3. ScriptRoutedOCR     - run the chain through run_with_escalation (primary -> cleaned retry ->
                           stronger engines), keeping the most-confident result and flagging the
                           rest downstream.

Chains currently keep Tesseract primary everywhere (no behavior change vs the old AUTO). When a
strong all-script engine (e.g. PaddleOCR-VL, GPU) is added it is registered here and moved to the
front of the CJK/Indic/Thai chains — the only change needed to reprioritize is this table.
"""

from __future__ import annotations

import io
import re

from ..config import Config
from ..ir import Block
from .auto import run_with_escalation

_OSD_SCRIPT = re.compile(r"Script:\s*([\w]+)")


def detect_script(img: bytes) -> str | None:
    """Tesseract OSD script name for a page image (e.g. 'Latin', 'Arabic', 'Han', 'Devanagari').
    None if undetectable — the router then uses the default chain."""
    try:
        import pytesseract
        from PIL import Image
        osd = pytesseract.image_to_osd(Image.open(io.BytesIO(img)))
    except Exception:
        return None
    m = _OSD_SCRIPT.search(osd)
    return m.group(1) if m else None


# ── engine registry ──────────────────────────────────────────────────────────────────────────
# name -> zero-arg builder. A builder returns None when its dependency isn't installed, so an
# unavailable engine simply drops out of every chain.
def _build_tesseract():
    from .tesseract import TesseractOCR
    return TesseractOCR()


def _build_paddle():
    try:
        import paddleocr  # noqa: F401
        from .paddle import PaddleOCREngine
        return PaddleOCREngine()
    except Exception:
        return None


def _build_easyocr():
    try:
        import easyocr  # noqa: F401
        from .easyocr_engine import EasyOCREngine
        return EasyOCREngine()
    except Exception:
        return None


def _build_paddle_vl():
    # Strongest all-script engine (PaddleOCR-VL, GPU). Boxes need the paddlepaddle pipeline, so it
    # runs in the isolated layout_venv subprocess (like PP-StructureV3) — added in a follow-up.
    try:
        from .paddle_vl import PaddleVLOCR
        return PaddleVLOCR()
    except Exception:
        return None


_BUILDERS = {
    "tesseract": _build_tesseract,
    "easyocr": _build_easyocr,
    "paddle": _build_paddle,
    "paddle_vl": _build_paddle_vl,
}

# Per-script engine chain (primary first, then escalation targets). paddle_vl is listed ahead of
# paddle for the scripts Tesseract is weak on; until it's installed the chain collapses to
# tesseract -> paddle, i.e. today's behavior. Unknown scripts use DEFAULT_CHAIN.
# Chain order: Tesseract primary (fast, cheap on clean pages) -> EasyOCR (strong multilingual,
# the real escalation) -> paddle_vl/paddle (max accuracy, when installed). A low-confidence page
# walks down the chain; a confident page stops early. Tesseract stays primary on every script so
# clean Latin/Arabic pages stay fast; the weak-script gains come from EasyOCR catching the misses.
DEFAULT_CHAIN = ["tesseract", "easyocr", "paddle_vl", "paddle"]
ROUTING: dict[str, list[str]] = {
    "Latin": ["tesseract", "easyocr", "paddle_vl"],
    "Cyrillic": ["tesseract", "easyocr", "paddle_vl"],
    "Greek": ["tesseract", "easyocr", "paddle_vl"],
    "Arabic": ["tesseract", "easyocr", "paddle_vl"],   # Surya excluded: catastrophic on Arabic
    "Hebrew": ["tesseract", "easyocr", "paddle_vl"],
    # Scripts where Tesseract is weak: EasyOCR (then paddle_vl/paddle) recovers the low-conf pages.
    "Han": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Hangul": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Japanese": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Devanagari": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Bengali": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Tamil": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Telugu": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Thai": ["tesseract", "easyocr", "paddle_vl", "paddle"],
    "Kannada": ["tesseract", "easyocr", "paddle_vl", "paddle"],
}


class ScriptRoutedOCR:
    name = "auto"

    def __init__(self):
        self._cache: dict[str, object] = {}      # engine name -> built engine (or None)

    def _engine(self, name: str):
        if name not in self._cache:
            builder = _BUILDERS.get(name)
            try:
                self._cache[name] = builder() if builder else None
            except Exception:
                self._cache[name] = None
        return self._cache[name]

    def _chain(self, img: bytes, cfg: Config) -> list[str]:
        # An explicit source language means we trust Tesseract's lang pack — keep it primary.
        if cfg.source_lang and cfg.source_lang != "auto":
            return DEFAULT_CHAIN
        script = detect_script(img)
        return ROUTING.get(script, DEFAULT_CHAIN)

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        engines = [self._engine(n) for n in self._chain(img, cfg)]
        if not any(engines):
            engines = [self._engine("tesseract")]
        return run_with_escalation(engines, img, cfg, page)
