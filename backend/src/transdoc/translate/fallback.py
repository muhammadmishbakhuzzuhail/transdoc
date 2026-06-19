# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Fallback router — the resilient default for the free public service.

Tries a chain of engines in order; if one raises (rate-limit, IP-block, network), it moves
to the next. This is what keeps a Google-web-endpoint-based service alive: when Google
blocks, requests fall through to MyMemory, then a self-hosted LibreTranslate backstop, and
finally an offline CTranslate2 engine (Argos) so the service NEVER fully fails when offline
models are installed.

Engines are constructed lazily and only added to the chain if usable (e.g. LibreTranslate is
skipped unless LIBRETRANSLATE_URL is set; Argos is skipped unless argostranslate is
installed). Per batch, the first engine that returns without raising wins.

Circuit breaker: a document is many batches. Without a breaker, every batch would burn the
full per-engine retry budget (Google does 5 exponential-backoff attempts) on an engine that
is already IP-blocked — tens of seconds wasted per batch. After TRANSDOC_BREAKER_FAILS
consecutive failures an engine's circuit opens for TRANSDOC_BREAKER_COOLDOWN seconds and is
skipped; a single success closes it again. Tripped engines are still tried as a last resort
if every healthy engine fails, so the breaker only ever reorders — it never gives up.

Env:
  TRANSDOC_FALLBACK_CHAIN   comma list, e.g. "google,mymemory,libretranslate"
                            (default: google,mymemory[,libretranslate if configured],argos)
  TRANSDOC_BREAKER_FAILS    consecutive failures before a circuit opens (default 2)
  TRANSDOC_BREAKER_COOLDOWN seconds a tripped circuit stays open (default 60)
"""

from __future__ import annotations

import os
import threading
import time

from ..config import Config

_BREAKER_FAILS = int(os.environ.get("TRANSDOC_BREAKER_FAILS", "2"))
_BREAKER_COOLDOWN = float(os.environ.get("TRANSDOC_BREAKER_COOLDOWN", "60"))


def _default_chain() -> list[str]:
    env = os.environ.get("TRANSDOC_FALLBACK_CHAIN", "")
    if env.strip():
        return [c.strip() for c in env.split(",") if c.strip()]
    chain = ["google", "mymemory"]
    if os.environ.get("LIBRETRANSLATE_URL"):
        chain.append("libretranslate")
    # Offline CTranslate2 backstop (MIT). Skipped at build time if argostranslate is absent,
    # so it costs nothing when not installed but guarantees no total failure when it is.
    chain.append("argos")
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
        # Circuit-breaker state, shared across the thread-based JobStore workers.
        self._lock = threading.Lock()
        self._fails: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

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

    def _order(self, engines: list) -> list:
        """Healthy engines first, engines with an open circuit last (still tried as a last
        resort so the breaker only reorders — it never abandons an engine entirely)."""
        now = time.monotonic()
        with self._lock:
            live = [e for e in engines if self._open_until.get(e.name, 0.0) <= now]
            tripped = [e for e in engines if self._open_until.get(e.name, 0.0) > now]
        return live + tripped

    def _record_ok(self, name: str) -> None:
        with self._lock:
            self._fails[name] = 0
            self._open_until.pop(name, None)

    def _record_fail(self, name: str) -> None:
        with self._lock:
            n = self._fails.get(name, 0) + 1
            self._fails[name] = n
            if n >= _BREAKER_FAILS:
                self._open_until[name] = time.monotonic() + _BREAKER_COOLDOWN

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        engines = self._ensure()
        if not engines:
            raise RuntimeError(f"no usable engine in fallback chain: {self._names}")
        last: Exception | None = None
        for eng in self._order(engines):
            try:
                out = eng.translate_batch(texts, cfg, src=src)
                self._record_ok(eng.name)
                return out
            except Exception as e:
                last = e
                self._record_fail(eng.name)
                continue
        raise RuntimeError(f"all fallback engines failed ({self._names}): {last}")
