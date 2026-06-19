# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""MyMemory translator — free fallback engine (no API key).

MyMemory gives ~50k words/day (with email) for free. Used as a mid-chain fallback when the
Google web endpoint fails. It expects locale-style codes (e.g. ``en-US``), so ISO 639-1
targets are mapped to a sensible regional variant.

Env:
  MYMEMORY_EMAIL   optional; raises the free daily quota when set
"""

from __future__ import annotations

import os

from ..config import Config

# ISO 639-1 -> MyMemory locale. Extend as needed.
_LOCALE = {
    "en": "en-US", "id": "id-ID", "ar": "ar-SA", "zh": "zh-CN", "ja": "ja-JP",
    "ko": "ko-KR", "ru": "ru-RU", "hi": "hi-IN", "th": "th-TH", "vi": "vi-VN",
    "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "pt": "pt-PT", "it": "it-IT",
    "nl": "nl-NL", "ms": "ms-MY", "tr": "tr-TR", "fa": "fa-IR",
}


class MyMemoryTranslator:
    name = "mymemory"

    def __init__(self):
        from deep_translator import MyMemoryTranslator as _M

        self._M = _M
        self._email = os.environ.get("MYMEMORY_EMAIL")

    def _code(self, lang: str | None, default: str) -> str:
        if not lang or lang == "auto":
            return default
        if "-" in lang:
            return lang
        return _LOCALE.get(lang, lang)

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        source = self._code(src or cfg.source_lang, "en-GB")
        target = self._code(cfg.target_lang, "en-US")
        kwargs = {"source": source, "target": target}
        if self._email:
            kwargs["email"] = self._email
        out: list[str] = []
        for t in texts:
            if not t.strip():
                out.append(t)
                continue
            eng = self._M(**kwargs)
            res = eng.translate(t)
            out.append(res if res is not None else t)
        return out
