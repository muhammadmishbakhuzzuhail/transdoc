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

import concurrent.futures
import os
import random
import threading
import time

from ..config import Config

# Google web endpoint rejects requests over ~5000 chars; stay safely under.
_MAX_CHARS = int(os.environ.get("GOOGLE_TRANSLATE_MAX_CHARS", "4500"))

# Translate a batch's segments concurrently — the slow part is N sequential HTTP round-trips,
# one per segment, so a thread pool cuts first-run time ~N×. Bounded to stay under the free
# endpoint's ban threshold; set 1 to force sequential. The per-call retry/backoff + optional
# throttle still apply inside each worker.
_CONCURRENCY = max(1, int(os.environ.get("GOOGLE_CONCURRENCY", "8")))

# Anti-ban throttle: the free Google web endpoint IP-bans at scale, so optionally hold a
# minimum gap between outbound requests (seconds; default 0 = off). The TM cache already
# means each unique segment is sent at most once, so a small interval is usually enough.
_MIN_INTERVAL = float(os.environ.get("GOOGLE_MIN_INTERVAL", "0"))
_throttle_lock = threading.Lock()
_last_call = [0.0]


def _throttle() -> None:
    if _MIN_INTERVAL <= 0:
        return
    with _throttle_lock:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()

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
        window = rest[:limit]
        # Prefer a sentence boundary: Latin ". ", a newline, or a CJK sentence-final mark
        # (。！？．) — CJK has no spaces, so the old space-split cut mid-sentence.
        cut = max(window.rfind(". "), window.rfind("\n"), window.rfind("。"),
                  window.rfind("！"), window.rfind("？"), window.rfind("．"))
        if cut >= limit // 2:
            cut += 1                      # keep the boundary char with the left chunk
        else:
            sp = window.rfind(" ")
            cut = sp + 1 if sp > 0 else limit
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

    def _make(self, source: str, target: str):
        """Build the engine, falling back to auto-detect if the source code is rejected
        (language detection can yield a bad/unsupported code on noisy OCR text)."""
        try:
            return self._G(source=source, target=target)
        except Exception:
            if source != "auto":
                return self._G(source="auto", target=target)
            raise

    def _translate_one(self, text: str, source: str, target: str) -> str:
        """Translate a single string (splitting if it exceeds the char cap), with backoff."""
        chunks = _split_long(text, _MAX_CHARS)
        out: list[str] = []
        for chunk in chunks:
            if not chunk.strip():
                out.append(chunk)
                continue
            last: Exception | None = None
            result: str | None = None
            for attempt in range(5):
                try:
                    _throttle()                       # optional anti-ban pacing
                    eng = self._make(source, target)
                    res = eng.translate(chunk)
                    # A throttled web endpoint can answer None/empty for non-empty input.
                    # Treat that as a soft failure and retry, rather than silently keeping the
                    # source text (which left whole pages untranslated in long documents).
                    if res is None or (chunk.strip() and not res.strip()):
                        raise ValueError("empty translation (endpoint throttled?)")
                    result = res
                    last = None
                    break
                except Exception as e:  # rate-limit / transient — exponential backoff + jitter
                    last = e
                    # jitter (±50%) so many concurrent retries don't resynchronise into a
                    # burst that looks like an attack and triggers a harder block.
                    time.sleep(0.6 * (2 ** attempt) * (1 + random.random() * 0.5))
            if last is not None:
                raise last  # retries exhausted -> let the fallback router try the next engine
            out.append(result if result is not None else chunk)
        return "".join(out)

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        source = self._code(src or cfg.source_lang)
        target = self._code(cfg.target_lang)

        def one(t: str) -> str:
            return self._translate_one(t, source, target) if t.strip() else t

        if _CONCURRENCY <= 1 or len(texts) <= 1:
            return [one(t) for t in texts]
        # ThreadPoolExecutor.map preserves input order; HTTP waits run in parallel.
        with concurrent.futures.ThreadPoolExecutor(max_workers=_CONCURRENCY) as ex:
            return list(ex.map(one, texts))
