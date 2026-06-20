# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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
    # PaddleOCR PP-OCRv5 — strongest on degraded/non-Latin scans. Runs in-process if paddle is
    # importable here, else via the isolated layout_venv subprocess (paddle/torch nccl clash).
    # (PaddleOCR-VL 0.9B was rejected: OOM on 6 GB GPU / 11 GB RAM — this is the classic pipeline.)
    try:
        from .paddle import PaddleOCREngine
        eng = PaddleOCREngine()
        return eng if eng.available else None
    except Exception:
        return None


def _build_easyocr():
    try:
        import easyocr  # noqa: F401
        from .easyocr_engine import EasyOCREngine
        return EasyOCREngine()
    except Exception:
        return None


_BUILDERS = {
    "tesseract": _build_tesseract,
    "easyocr": _build_easyocr,
    "paddle": _build_paddle,
}

# Per-script engine chain (primary first, then escalation targets). paddle_vl is listed ahead of
# paddle for the scripts Tesseract is weak on; until it's installed the chain collapses to
# tesseract -> paddle, i.e. today's behavior. Unknown scripts use DEFAULT_CHAIN.
# Chain order (precision-first). PaddleOCR PP-OCRv5 is the most accurate engine and, with the
# paddle-GPU layout_venv, runs ~1 s/page on a 6 GB card, so it leads on every script Tesseract is
# weak at (CJK/Indic/Thai). On Latin/Cyrillic/Greek/Arabic/Hebrew, Tesseract leads (near-equal
# accuracy, faster) and Paddle is the escalation. EasyOCR is the last-resort fallback (CPU only;
# its GPU path OOMs on small cards). A low-confidence/weak-tail page walks down the chain; a
# confident page stops early.
DEFAULT_CHAIN = ["tesseract", "paddle", "easyocr"]
ROUTING: dict[str, list[str]] = {
    "Latin": ["tesseract", "paddle", "easyocr"],
    "Cyrillic": ["tesseract", "paddle", "easyocr"],
    "Greek": ["tesseract", "paddle", "easyocr"],
    "Arabic": ["tesseract", "paddle", "easyocr"],      # Surya excluded: catastrophic on Arabic
    "Hebrew": ["tesseract", "paddle", "easyocr"],
    # Scripts where Tesseract is weak: PaddleOCR (precise + GPU-fast) leads, Tesseract/EasyOCR back it.
    "Han": ["paddle", "tesseract", "easyocr"],
    "Hangul": ["paddle", "tesseract", "easyocr"],
    "Japanese": ["paddle", "tesseract", "easyocr"],
    "Devanagari": ["paddle", "tesseract", "easyocr"],
    "Bengali": ["paddle", "tesseract", "easyocr"],
    "Tamil": ["paddle", "tesseract", "easyocr"],
    "Telugu": ["paddle", "tesseract", "easyocr"],
    # Tesseract mangles Thai — it inserts spurious spaces between syllable clusters
    # ("ปฏิญญา" -> "ป ฏิ ญ ญ า") yet reports high confidence, so it wins escalation over the
    # correct-but-lower-confidence Paddle pass and wrecks the translation. Drop it from the chain;
    # Paddle leads and EasyOCR (no spurious spacing) backs it up.
    "Thai": ["paddle", "easyocr"],
    "Kannada": ["paddle", "tesseract", "easyocr"],
    # Indic scripts only Tesseract has models for (Paddle/EasyOCR lack them) -> tesseract leads,
    # the others are no-ops that simply drop out of the chain. Explicit so routing is intentional,
    # not an accident of DEFAULT_CHAIN.
    "Malayalam": ["tesseract", "paddle", "easyocr"],
    "Gujarati": ["tesseract", "paddle", "easyocr"],
    "Gurmukhi": ["tesseract", "paddle", "easyocr"],
    "Oriya": ["tesseract", "paddle", "easyocr"],
    "Sinhala": ["tesseract", "paddle", "easyocr"],
}

# Explicit source language -> its script, so an explicit non-Latin --source still gets the
# script-optimised chain (paddle-first) instead of the tesseract-first default. Without this, e.g.
# `--source hi` on a Devanagari scan routes to Tesseract, which is weak on Devanagari and returns
# garbage at a falsely-high confidence (so it never escalates to Paddle, which OCRs it perfectly).
# Latin-script languages are intentionally absent: they keep the tesseract-first DEFAULT_CHAIN.
LANG_TO_SCRIPT: dict[str, str] = {
    "hi": "Devanagari", "mr": "Devanagari", "ne": "Devanagari", "sa": "Devanagari",
    "zh": "Han", "zh-hans": "Han", "zh-cn": "Han", "zh-hant": "Han", "zh-tw": "Han",
    "ja": "Japanese", "ko": "Hangul",
    "bn": "Bengali", "ta": "Tamil", "te": "Telugu", "th": "Thai", "kn": "Kannada",
    "ru": "Cyrillic", "uk": "Cyrillic", "bg": "Cyrillic", "sr": "Cyrillic",
    "ar": "Arabic", "fa": "Arabic", "ur": "Arabic", "he": "Hebrew", "el": "Greek",
    "ml": "Malayalam", "gu": "Gujarati", "pa": "Gurmukhi", "or": "Oriya", "si": "Sinhala",
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
        src = (cfg.source_lang or "auto").lower()
        if src != "auto":
            # An explicit NON-Latin source still needs its script-optimised chain (paddle-first) —
            # Tesseract is weak on Devanagari/CJK/Indic even with the lang pack. A Latin/unknown
            # explicit source keeps the tesseract-first default (fast, and the lang pack is good).
            script = LANG_TO_SCRIPT.get(src)
            return ROUTING.get(script, DEFAULT_CHAIN) if script else DEFAULT_CHAIN
        return ROUTING.get(detect_script(img), DEFAULT_CHAIN)

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        engines = [self._engine(n) for n in self._chain(img, cfg)]
        if not any(engines):
            engines = [self._engine("tesseract")]
        return run_with_escalation(engines, img, cfg, page)
