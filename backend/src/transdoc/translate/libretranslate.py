# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""LibreTranslate translator — the resilient self-host backstop + privacy/offline mode.

Self-hosted LibreTranslate needs NO API key and has no external quota (limits are operator
-controlled), so it keeps the service alive when the Google web endpoint is rate-limited or
IP-blocked. It is also the privacy/offline engine: documents never leave your infrastructure.

LICENSE NOTE: LibreTranslate is AGPL-3.0 (network-copyleft). Running it as a SEPARATE
service (its own process / Docker container) that transdoc only calls over HTTP keeps it at
arm's length — transdoc imports none of its code. Confirm before bundling.

Env:
  LIBRETRANSLATE_URL       base URL of the instance (default http://localhost:5000)
  LIBRETRANSLATE_API_KEY   optional; only needed for instances configured with keys
"""

from __future__ import annotations

import os

from ..config import Config

_DEFAULT_URL = os.environ.get("LIBRETRANSLATE_URL", "http://localhost:5000")


class LibreTranslateTranslator:
    name = "libretranslate"

    def __init__(self):
        from deep_translator import LibreTranslator as _L

        self._L = _L
        self._url = os.environ.get("LIBRETRANSLATE_URL", _DEFAULT_URL)
        self._key = os.environ.get("LIBRETRANSLATE_API_KEY")

    def _code(self, lang: str | None, default: str) -> str:
        if not lang or lang == "auto":
            return default
        return lang

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        source = self._code(src or cfg.source_lang, "auto")
        target = self._code(cfg.target_lang, "en")
        kwargs = {"base_url": self._url, "source": source, "target": target}
        if self._key:
            kwargs["api_key"] = self._key
        out: list[str] = []
        for t in texts:
            if not t.strip():
                out.append(t)
                continue
            eng = self._L(**kwargs)
            res = eng.translate(t)
            out.append(res if res is not None else t)
        return out
