# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Fallback router: first engine that doesn't raise wins; chain config is honored."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.translate import fallback as fb


class _Boom:
    name = "boom"

    def translate_batch(self, texts, cfg, src=None):
        raise RuntimeError("rate-limited")


class _Ok:
    def __init__(self, tag):
        self.name = tag

    def translate_batch(self, texts, cfg, src=None):
        return [f"{self.name}:{t}" for t in texts]


def test_default_chain_is_google_mymemory_then_offline_backstop(monkeypatch):
    monkeypatch.delenv("TRANSDOC_FALLBACK_CHAIN", raising=False)
    monkeypatch.delenv("LIBRETRANSLATE_URL", raising=False)
    # argos is the offline CTranslate2 backstop (skipped at build time if not installed)
    assert fb._default_chain() == ["google", "mymemory", "argos"]


def test_chain_adds_libretranslate_when_configured(monkeypatch):
    monkeypatch.delenv("TRANSDOC_FALLBACK_CHAIN", raising=False)
    monkeypatch.setenv("LIBRETRANSLATE_URL", "http://localhost:5000")
    assert fb._default_chain() == ["google", "mymemory", "libretranslate", "argos"]


def test_env_overrides_chain(monkeypatch):
    monkeypatch.setenv("TRANSDOC_FALLBACK_CHAIN", "mymemory, google ,argos")
    assert fb._default_chain() == ["mymemory", "google", "argos"]


def test_falls_through_to_next_engine_on_error(monkeypatch):
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a", "b"])
    monkeypatch.setattr(fb, "_build", lambda n: _Boom() if n == "a" else _Ok("b"))
    tr = fb.FallbackTranslator()
    assert tr.translate_batch(["x"], Config(target_lang="id")) == ["b:x"]


def test_raises_when_all_engines_fail(monkeypatch):
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a", "b"])
    monkeypatch.setattr(fb, "_build", lambda n: _Boom())
    tr = fb.FallbackTranslator()
    with pytest.raises(RuntimeError, match="all fallback engines failed"):
        tr.translate_batch(["x"], Config(target_lang="id"))


def test_unbuildable_engines_are_skipped(monkeypatch):
    def build(n):
        if n == "a":
            raise ImportError("missing dep")
        return _Ok("b")

    monkeypatch.setattr(fb, "_default_chain", lambda: ["a", "b"])
    monkeypatch.setattr(fb, "_build", build)
    tr = fb.FallbackTranslator()
    assert tr.translate_batch(["x"], Config(target_lang="id")) == ["b:x"]


def test_empty_input_returns_empty(monkeypatch):
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a"])
    monkeypatch.setattr(fb, "_build", lambda n: _Ok("a"))
    assert fb.FallbackTranslator().translate_batch([], Config(target_lang="id")) == []


class _CountingBoom:
    def __init__(self, tag):
        self.name = tag
        self.calls = 0

    def translate_batch(self, texts, cfg, src=None):
        self.calls += 1
        raise RuntimeError("rate-limited")


def test_circuit_breaker_skips_dead_engine_after_threshold(monkeypatch):
    """A consistently-failing engine stops being retried once its circuit opens, so later
    batches don't keep burning its retry budget."""
    monkeypatch.setattr(fb, "_BREAKER_FAILS", 2)
    monkeypatch.setattr(fb, "_BREAKER_COOLDOWN", 9999)
    boom, ok = _CountingBoom("a"), _Ok("b")
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a", "b"])
    monkeypatch.setattr(fb, "_build", lambda n: boom if n == "a" else ok)
    tr = fb.FallbackTranslator()
    cfg = Config(target_lang="id")
    for _ in range(5):
        assert tr.translate_batch(["x"], cfg) == ["b:x"]
    # 'a' is tried on batches 1 and 2 (2nd trips the breaker), then skipped on 3,4,5.
    assert boom.calls == 2


def test_success_resets_breaker(monkeypatch):
    monkeypatch.setattr(fb, "_BREAKER_FAILS", 2)
    monkeypatch.setattr(fb, "_BREAKER_COOLDOWN", 9999)
    flap = _CountingBoom("a")
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a"])
    monkeypatch.setattr(fb, "_build", lambda n: flap)
    tr = fb.FallbackTranslator()
    cfg = Config(target_lang="id")
    # one failure (below threshold) then success closes any partial state
    with pytest.raises(RuntimeError):
        tr.translate_batch(["x"], cfg)
    flap.translate_batch = lambda texts, cfg, src=None: [f"a:{t}" for t in texts]
    assert tr.translate_batch(["x"], cfg) == ["a:x"]


def test_tripped_engine_still_tried_as_last_resort(monkeypatch):
    """If every healthy engine fails, an open-circuit engine is still attempted — the breaker
    only reorders, it never abandons an engine."""
    monkeypatch.setattr(fb, "_BREAKER_FAILS", 1)
    monkeypatch.setattr(fb, "_BREAKER_COOLDOWN", 9999)
    recovering = _CountingBoom("a")
    other = _Boom()
    monkeypatch.setattr(fb, "_default_chain", lambda: ["a", "boom"])
    monkeypatch.setattr(fb, "_build", lambda n: recovering if n == "a" else other)
    tr = fb.FallbackTranslator()
    cfg = Config(target_lang="id")
    # batch 1: a fails (trips immediately, FAILS=1), boom fails -> RuntimeError
    with pytest.raises(RuntimeError):
        tr.translate_batch(["x"], cfg)
    # a has recovered; even though its circuit is open it is tried (as last resort here it is
    # first since both are tripped) and now succeeds
    recovering.translate_batch = lambda texts, cfg, src=None: [f"a:{t}" for t in texts]
    assert tr.translate_batch(["x"], cfg) == ["a:x"]
