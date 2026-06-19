# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""REST feedback API (PR-5): glossary CRUD, suggestion accept, correction, tm stats/confirm/purge,
and the per-job review payload. Localhost-trust; every write mirrors the CLI/store behaviour."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.glossary import GlossaryStore
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    GlossaryStore._instance = None
    from transdoc.api.app import app
    yield TestClient(app)
    TMStore._instance = None
    GlossaryStore._instance = None


def test_glossary_add_list_remove(client):
    r = client.post("/api/glossary", json={"term": "Mark", "rendering": "tanda",
                                           "src_lang": "de", "tgt_lang": "id", "locked": True})
    assert r.status_code == 200 and r.json()["ok"]
    entries = client.get("/api/glossary", params={"src_lang": "de", "tgt_lang": "id"}).json()["entries"]
    assert entries[0]["term"] == "Mark" and entries[0]["locked"] == 1
    r = client.request("DELETE", "/api/glossary",
                       json={"term": "Mark", "src_lang": "de", "tgt_lang": "id"})
    assert r.json()["removed"] == 1


def test_correct_segment_and_term(client):
    r = client.post("/api/correct", json={"source": "Guten Morgen", "fix": "Selamat pagi",
                                          "src_lang": "de", "tgt_lang": "id"})
    assert r.json()["scope"] == "segment"
    r = client.post("/api/correct", json={"source": "Mark", "fix": "tanda", "src_lang": "de",
                                          "tgt_lang": "id", "term": True})
    assert r.json()["scope"] == "term"
    entries = client.get("/api/glossary", params={"src_lang": "de", "tgt_lang": "id"}).json()["entries"]
    assert any(e["term"] == "Mark" and e["rendering"] == "tanda" for e in entries)


def test_suggestion_list_and_accept(client):
    from transdoc.store.glossary import GlossaryStore
    GlossaryStore.get().add_suggestions([("Transdoc", "Transdoc-ID")], "en", "id")
    sug = client.get("/api/glossary/suggestions", params={"src_lang": "en"}).json()["suggestions"]
    assert sug[0]["term"] == "Transdoc"
    r = client.post("/api/glossary/suggestions/accept",
                    json={"term": "Transdoc", "src_lang": "en", "tgt_lang": "id"})
    assert r.json()["ok"]
    assert client.get("/api/glossary/suggestions").json()["suggestions"] == []
    r = client.post("/api/glossary/suggestions/accept",
                    json={"term": "Nope", "src_lang": "en", "tgt_lang": "id"})
    assert r.status_code == 404


def test_tm_stats_confirm_purge(client):
    from transdoc.store.tm import TMStore
    tm = TMStore.get()
    tm.put_many({"keep": "e1", "drop": "e2"}, "id", src_lang="en")
    assert client.get("/api/tm/stats").json()["total"] == 2
    assert client.post("/api/tm/confirm",
                       json={"source": "keep", "tgt_lang": "id", "src_lang": "en"}).json()["confirmed"] == 1
    assert client.post("/api/tm/purge", json={}).json()["purged"] == 1
    assert client.get("/api/tm/stats").json()["confirmed"] == 1


def test_review_endpoint(client, tmp_path, monkeypatch):
    from transdoc.api import jobs
    job = jobs.store.create("in.txt", {})
    out_dir = jobs.store.work_dir / job.id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review.json").write_text(json.dumps(
        {"src_lang": "en", "tgt_lang": "id", "segments": [
            {"block_id": "b1", "page": 0, "source": "Hi", "translation": "Hai", "flags": []}],
         "glossary_suggestions": [], "fuzzy_suggestions": []}))
    job.output_path = str(out_dir / "translated.md")
    jobs.store._save(job)
    r = client.get(f"/api/review/{job.id}")
    assert r.status_code == 200 and r.json()["segments"][0]["translation"] == "Hai"
    assert client.get("/api/review/nope").status_code == 404
