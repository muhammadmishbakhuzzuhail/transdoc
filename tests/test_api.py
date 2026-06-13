"""API surface for the React UI: enriched /api/health, translate with the new options, and
the /api/analysis endpoint that backs the analysis panels. Uses the echo engine (no network)."""

from __future__ import annotations

import io
import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from transdoc.api.app import app  # noqa: E402

client = TestClient(app)


def test_health_lists_all_option_sets():
    h = client.get("/api/health").json()
    for key in ("engines", "formats", "fidelity", "ocr", "register", "layout"):
        assert key in h and h[key]
    assert "paddle" in h["layout"]


def _run_echo_job(**extra):
    files = {"file": ("t.txt", io.BytesIO(b"Hello world. This is a short test document."),
                      "text/plain")}
    data = {"target_lang": "id", "engine": "echo", "output_format": "markdown", **extra}
    r = client.post("/api/translate", files=files, data=data)
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]
    for _ in range(100):
        j = client.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert j["status"] == "done", j
    return jid


def test_translate_accepts_new_options_and_serves_analysis():
    jid = _run_echo_job(layout="off", quality="false", bilingual="false")
    a = client.get(f"/api/analysis/{jid}")
    assert a.status_code == 200
    aj = a.json()
    assert set(aj) >= {"profile", "counts", "rendering", "layout", "flagged", "glossary",
                       "repairs"}
    assert aj["counts"]["blocks"] >= 1
    assert aj["profile"]["input_nature"]  # populated by diagnose


def test_analysis_404_for_unknown_job():
    assert client.get("/api/analysis/deadbeef").status_code == 404
