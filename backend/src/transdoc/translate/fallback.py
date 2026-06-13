"""Fallback router — the resilient default for the free public service.

Tries a chain of engines in order; if one raises (rate-limit, IP-block, network), it moves
to the next. This is what keeps a Google-web-endpoint-based service alive: when Google
blocks, requests fall through to MyMemory and finally a self-hosted LibreTranslate backstop.

Engines are constructed lazily and only added to the chain if usable (e.g. LibreTranslate is
skipped unless LIBRETRANSLATE_URL is reachable-by-config). Per batch, the first engine that
returns without raising wins.

Env:
  TRANSDOC_FALLBACK_CHAIN   comma list, e.g. "google,mymemory,libretranslate"
                            (default: google,mymemory[,libretranslate if configured])
"""

from __future__ import annotations

import os

from ..config import Config


def _default_chain() -> list[str]:
    env = os.environ.get("TRANSDOC_FALLBACK_CHAIN", "")
    if env.strip():
        return [c.strip() for c in env.split(",") if c.strip()]
    chain = ["google", "mymemory"]
    if os.environ.get("LIBRETRANSLATE_URL"):
        chain.append("libretranslate")
    return chain


def _build(name: str):
    if name == "google":
        from .google import GoogleTranslator
        return GoogleTranslator()
    if name == "mymemory":
        from .mymemory import MyMemoryTranslator
        return MyMemoryTranslator()
    if name == "libretranslate":
        from .libretranslate import LibreTranslateTranslator
        return LibreTranslateTranslator()
    if name == "madlad":
        from .madlad import MadladTranslator
        return MadladTranslator()
    if name == "argos":
        from .argos import ArgosTranslator
        return ArgosTranslator()
    raise ValueError(f"engine not allowed in fallback chain: {name}")


class FallbackTranslator:
    name = "fallback"

    def __init__(self):
        self._names = _default_chain()
        # Construct lazily on first use so a missing optional dep doesn't break the chain.
        self._engines: list[object] | None = None

    def _ensure(self) -> list:
        if self._engines is None:
            built = []
            for n in self._names:
                try:
                    built.append(_build(n))
                except Exception:
                    continue  # skip engines that can't initialize
            self._engines = built
        return self._engines

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        engines = self._ensure()
        if not engines:
            raise RuntimeError(f"no usable engine in fallback chain: {self._names}")
        last: Exception | None = None
        for eng in engines:
            try:
                return eng.translate_batch(texts, cfg, src=src)
            except Exception as e:
                last = e
                continue
        raise RuntimeError(f"all fallback engines failed ({self._names}): {last}")
