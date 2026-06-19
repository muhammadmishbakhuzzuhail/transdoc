# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""JobStore: SQLite persistence, cross-instance visibility, restart recovery."""

from __future__ import annotations

import time

from transdoc.api.jobs import JobStore
from transdoc.config import Config, Engine, OutputFormat


def _store(tmp_path) -> JobStore:
    return JobStore(work_dir=str(tmp_path / "work"), db_path=str(tmp_path / "jobs.sqlite"))


def test_create_and_get_persists(tmp_path):
    s = _store(tmp_path)
    job = s.create("in.txt", meta={"filename": "in.txt"})
    got = s.get(job.id)
    assert got is not None
    assert got.status == "queued"
    assert got.meta == {"filename": "in.txt"}


def test_get_unknown_returns_none(tmp_path):
    assert _store(tmp_path).get("does-not-exist") is None


def test_job_visible_across_instances(tmp_path):
    db = str(tmp_path / "jobs.sqlite")
    work = str(tmp_path / "work")
    s1 = JobStore(work_dir=work, db_path=db)
    job = s1.create("in.txt", meta={})
    # a second process/worker opening the same DB sees the row
    s2 = JobStore(work_dir=work, db_path=db)
    assert s2.get(job.id) is not None


def test_restart_recovers_orphaned_running_job(tmp_path):
    db = str(tmp_path / "jobs.sqlite")
    work = str(tmp_path / "work")
    s1 = JobStore(work_dir=work, db_path=db)
    job = s1.create("in.txt", meta={})
    job.status = "running"
    s1._save(job)
    # simulate a crash + restart: a fresh store opening the same DB
    s2 = JobStore(work_dir=work, db_path=db)
    recovered = s2.get(job.id)
    assert recovered.status == "error"
    assert "interrupted by restart" in recovered.message


def test_run_async_completes_job_with_echo_engine(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("Hello world.\n", encoding="utf-8")
    s = _store(tmp_path)
    job = s.create(str(src), meta={"filename": "in.txt"})
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.MARKDOWN)
    s.run_async(job, cfg)

    deadline = time.time() + 20
    while time.time() < deadline:
        cur = s.get(job.id)
        if cur.status in ("done", "error"):
            break
        time.sleep(0.05)

    final = s.get(job.id)
    assert final.status == "done", final.error
    assert final.output_path and final.progress == 1.0
