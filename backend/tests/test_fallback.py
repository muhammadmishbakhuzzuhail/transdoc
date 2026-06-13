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


def test_default_chain_is_google_then_mymemory(monkeypatch):
    monkeypatch.delenv("TRANSDOC_FALLBACK_CHAIN", raising=False)
    monkeypatch.delenv("LIBRETRANSLATE_URL", raising=False)
    assert fb._default_chain() == ["google", "mymemory"]


def test_chain_adds_libretranslate_when_configured(monkeypatch):
    monkeypatch.delenv("TRANSDOC_FALLBACK_CHAIN", raising=False)
    monkeypatch.setenv("LIBRETRANSLATE_URL", "http://localhost:5000")
    assert fb._default_chain() == ["google", "mymemory", "libretranslate"]


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
