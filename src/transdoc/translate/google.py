"""Google web-endpoint translator — the DocTranslator economics model.

Proxies the free public Google Translate web endpoint via ``deep-translator`` (MIT). The
server hosts NO model, so this runs CPU-only and translation cost is ~$0. This is the
DEFAULT engine for the free public service.

CAVEAT (verified): the Google web endpoint is unofficial and ToS-grey. It can rate-limit or
IP-block at scale. Do NOT rely on it as the sole engine — pair it with a fallback chain
(see ``fallback.py``: google -> mymemory -> libretranslate). Placeholder tokens used by
``protect.py`` (``[PH0]``) were tested and survive Google intact.

Env:
  GOOGLE_TRANSLATE_MAX_CHARS   per-request char cap (default 4500; Google hard limit ~5000)
"""

from __future__ import annotations

import os
import time

from ..config import Config

# Google web endpoint rejects requests over ~5000 chars; stay safely under.
_MAX_CHARS = int(os.environ.get("GOOGLE_TRANSLATE_MAX_CHARS", "4500"))

# Google/deep-translator use a few non-ISO-639-1 codes. Normalize the common ISO inputs
# so callers can pass the familiar code (e.g. "zh") and still hit Google. Anything not here
# is passed through unchanged.
_LANG_FIX = {
    "zh": "zh-CN", "zh-hans": "zh-CN", "zh_cn": "zh-CN", "zh-cn": "zh-CN",
    "zh-hant": "zh-TW", "zh_tw": "zh-TW", "zh-tw": "zh-TW",
    "he": "iw",   # Google's legacy code for Hebrew
    "jv": "jw",   # Javanese
}


def _split_long(text: str, limit: int) -> list[str]:
    """Split a single oversized segment on sentence/space boundaries, under ``limit``."""
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind(". ", 0, limit)
        if cut < limit // 2:
            cut = rest.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        else:
            cut += 1
        parts.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        parts.append(rest)
    return parts


class GoogleTranslator:
    name = "google"

    def __init__(self):
        from deep_translator import GoogleTranslator as _G

        self._G = _G

    def _code(self, lang: str | None) -> str:
        if not lang or lang == "auto":
            return "auto"
        return _LANG_FIX.get(lang.lower(), lang)

    def _translate_one(self, text: str, source: str, target: str) -> str:
        """Translate a single string (splitting if it exceeds the char cap), with backoff."""
        chunks = _split_long(text, _MAX_CHARS)
        out: list[str] = []
        for chunk in chunks:
            if not chunk.strip():
                out.append(chunk)
                continue
            last: Exception | None = None
            for attempt in range(4):
                try:
                    eng = self._G(source=source, target=target)
                    res = eng.translate(chunk)
                    out.append(res if res is not None else chunk)
                    last = None
                    break
                except Exception as e:  # rate-limit / transient — exponential backoff
                    last = e
                    time.sleep(0.5 * (2 ** attempt))
            if last is not None:
                raise last  # let the fallback router try the next engine
        return "".join(out)

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        source = self._code(src or cfg.source_lang)
        target = self._code(cfg.target_lang)
        return [self._translate_one(t, source, target) if t.strip() else t for t in texts]
