# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Review suggestion engine: synonym / rephrase parsing + the API endpoints. The LLM is stubbed
(the real Qwen model needs the [suggest] extra + a GPU); these cover the prompt/parse/route logic
and the graceful 503 when the model is unavailable."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.translate.suggest import STYLE_DIRECTIVES, Suggester, SuggestError


def _cfg():
    return Config(source_lang="auto", target_lang="id")


def test_synonyms_parse_and_exclude_original(monkeypatch):
    monkeypatch.setattr(Suggester, "_chat",
                        lambda self, s, u, **k: '{"synonyms": ["cepat", "lekas", "kilat", "cepat"]}')
    out = Suggester().synonyms("cepat", "Mobil itu cepat sekali.", _cfg(), n=6)
    assert out == ["lekas", "kilat"]          # deduped + original "cepat" excluded


def test_rephrase_parse_and_style(monkeypatch):
    seen = {}
    monkeypatch.setattr(Suggester, "_chat",
                        lambda self, s, u, **k: seen.update(sys=s) or '{"rephrasings": ["a", "b"]}')
    out = Suggester().rephrase("Halo dunia.", _cfg(), style="academic", n=2)
    assert out == ["a", "b"]
    assert STYLE_DIRECTIVES["academic"] in seen["sys"]      # style directive woven into the prompt


def test_parse_tolerates_code_fence(monkeypatch):
    monkeypatch.setattr(Suggester, "_chat",
                        lambda self, s, u, **k: '```json\n{"synonyms": ["x", "y"]}\n```')
    assert Suggester().synonyms("z", "z here", _cfg()) == ["x", "y"]


def test_parse_raises_on_garbage(monkeypatch):
    monkeypatch.setattr(Suggester, "_chat", lambda self, s, u, **k: "not json at all")
    with pytest.raises(SuggestError):
        Suggester().synonyms("z", "z", _cfg())


def test_empty_inputs_short_circuit():
    assert Suggester().synonyms("", "ctx", _cfg()) == []
    assert Suggester().rephrase("  ", _cfg()) == []


def test_release_resets_state():
    Suggester._model = "x"
    Suggester._ok = False
    Suggester.release()
    assert Suggester._model is None and Suggester._ok is True


# --- API endpoints (stub the engine) ---------------------------------------------------------

def _client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from transdoc.api.app import app
    return TestClient(app)


def test_synonyms_endpoint(monkeypatch):
    monkeypatch.setattr(Suggester, "synonyms", lambda self, p, c, cfg, n=6: ["alt1", "alt2"])
    r = _client().post("/api/synonyms", json={"phrase": "cepat", "context": "x", "tgt_lang": "id"})
    assert r.status_code == 200 and r.json()["synonyms"] == ["alt1", "alt2"]


def test_rephrase_endpoint(monkeypatch):
    monkeypatch.setattr(Suggester, "rephrase",
                        lambda self, s, cfg, style="general", n=3: [f"{style}:rewrite"])
    r = _client().post("/api/rephrase",
                       json={"sentence": "Halo.", "tgt_lang": "id", "style": "friendly"})
    assert r.status_code == 200 and r.json()["rephrasings"] == ["friendly:rewrite"]


def test_synonyms_503_when_model_unavailable(monkeypatch):
    def boom(self, p, c, cfg, n=6):
        raise SuggestError("no transformers")
    monkeypatch.setattr(Suggester, "synonyms", boom)
    r = _client().post("/api/synonyms", json={"phrase": "x", "context": "y", "tgt_lang": "id"})
    assert r.status_code == 503
