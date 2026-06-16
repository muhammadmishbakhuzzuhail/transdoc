"""Batch upload (one independent job per file, shared batch_id, serialised execution)."""

from __future__ import annotations

import io
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSDOC_JOBS_DB", str(tmp_path / "jobs.sqlite"))
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    # fresh JobStore bound to the tmp DB
    import transdoc.api.jobs as jobs_mod
    jobs_mod.store = jobs_mod.JobStore(work_dir=str(tmp_path / "work"),
                                       db_path=str(tmp_path / "jobs.sqlite"))
    import transdoc.api.app as app_mod
    app_mod.store = jobs_mod.store
    return TestClient(app_mod.app)


def _txt(name: str) -> tuple:
    return ("files", (name, io.BytesIO(b"Hello world. This is a test."), "text/plain"))


def test_batch_creates_one_job_per_file_with_shared_id(client):
    r = client.post("/api/batch",
                    files=[_txt("a.txt"), _txt("b.txt"), _txt("c.txt")],
                    data={"target_lang": "id", "engine": "echo",
                          "output_format": "markdown"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["jobs"]) == 3
    bid = body["batch_id"]
    assert {j["filename"] for j in body["jobs"]} == {"a.txt", "b.txt", "c.txt"}

    # poll the batch until all jobs settle
    for _ in range(100):
        s = client.get(f"/api/batch/{bid}").json()
        if all(j["status"] in ("done", "error") for j in s["jobs"]):
            break
        time.sleep(0.1)
    s = client.get(f"/api/batch/{bid}")
    assert s.status_code == 200
    assert len(s.json()["jobs"]) == 3


def test_batch_unknown_id_404(client):
    assert client.get("/api/batch/deadbeef").status_code == 404


def test_empty_batch_rejected(client):
    # no files part -> FastAPI validation 422 (File(...) required)
    r = client.post("/api/batch", data={"target_lang": "id"})
    assert r.status_code in (400, 422)
