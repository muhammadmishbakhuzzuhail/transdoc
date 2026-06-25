# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Shared test setup.

Disable the cross-run persistent translation memory for the whole test session. Otherwise a
test using the ECHO engine can read a real translation cached by an earlier real run (the cache
is consulted before the engine), so e.g. "Name" comes back as "Nama" instead of echo's "[id]
Name" — a non-deterministic failure that depends on the developer's local TM. Tests must not
depend on that shared cache.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_persistent_tm():
    prev = os.environ.get("TRANSDOC_TM_DISABLE")
    os.environ["TRANSDOC_TM_DISABLE"] = "1"
    yield
    if prev is None:
        os.environ.pop("TRANSDOC_TM_DISABLE", None)
    else:
        os.environ["TRANSDOC_TM_DISABLE"] = prev


@pytest.fixture(autouse=True, scope="session")
def _disable_structured_layout():
    """Force the heuristic extract path in tests: PP-StructureV3 (now the production default) is
    slow + needs paddle, so tests must not take it (fast + deterministic regardless of a local
    layout_venv). Production keeps layout=auto."""
    prev = os.environ.get("TRANSDOC_LAYOUT_DISABLE")
    os.environ["TRANSDOC_LAYOUT_DISABLE"] = "1"
    yield
    if prev is None:
        os.environ.pop("TRANSDOC_LAYOUT_DISABLE", None)
    else:
        os.environ["TRANSDOC_LAYOUT_DISABLE"] = prev


@pytest.fixture(autouse=True)
def _isolate_global_stores(tmp_path, monkeypatch):
    """Hermetic per-test state. The job store, TM and glossary are process-global singletons; the
    job `store` even defaults to a SHARED /tmp/transdoc_jobs sqlite. Without isolation, suites
    cross-contaminate (and the echo-job tests flake) and tests touch the developer's real
    ~/.local/share/transdoc data. Pin every store under tmp_path and rebind the job-store singleton
    everywhere it's referenced (app.py binds it at import, feedback_routes reads it lazily)."""
    jobs_dir = tmp_path / "jobs"
    monkeypatch.setenv("TRANSDOC_JOBS_DIR", str(jobs_dir))
    monkeypatch.setenv("TRANSDOC_JOBS_DB", str(jobs_dir / "jobs.sqlite"))
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "transdoc.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))

    from transdoc.api import app as app_mod
    from transdoc.api import jobs as jobs_mod
    from transdoc.store.glossary import GlossaryStore
    from transdoc.store.tm import TMStore

    fresh = jobs_mod.JobStore(work_dir=str(jobs_dir))
    monkeypatch.setattr(jobs_mod, "store", fresh)
    monkeypatch.setattr(app_mod, "store", fresh, raising=False)
    TMStore._instance = None
    GlossaryStore._instance = None
    yield
    TMStore._instance = None
    GlossaryStore._instance = None
