# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""LLM alternative-translation endpoint (review aid). Ollama is mocked — no real model call."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from transdoc.api.app import app
    return TestClient(app)


def test_alternatives_returns_variants(client, monkeypatch):
    from transdoc.translate import ollama
    monkeypatch.setattr(ollama.OllamaTranslator, "alternatives",
                        lambda self, text, cfg, src=None, n=3: ["Halo", "Hai", "Salam"])
    r = client.post("/api/alternatives", json={"source": "Hello", "tgt_lang": "id", "src_lang": "en"})
    assert r.status_code == 200
    assert r.json()["alternatives"] == ["Halo", "Hai", "Salam"]


def test_alternatives_503_when_llm_down(client, monkeypatch):
    from transdoc.translate import ollama

    def boom(*a, **k):
        raise ollama.OllamaError("connection refused")
    monkeypatch.setattr(ollama.OllamaTranslator, "alternatives", boom)
    r = client.post("/api/alternatives", json={"source": "Hello", "tgt_lang": "id"})
    assert r.status_code == 503


def test_alternatives_empty_source(client):
    r = client.post("/api/alternatives", json={"source": "   ", "tgt_lang": "id"})
    assert r.status_code == 200 and r.json()["alternatives"] == []
