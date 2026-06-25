# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""JobStore: SQLite persistence, cross-instance visibility, restart recovery."""

from __future__ import annotations

import threading
import time

from transdoc.api.jobs import JobStore
from transdoc.config import Config, Engine, OutputFormat


def _store(tmp_path) -> JobStore:
    return JobStore(work_dir=str(tmp_path / "work"), db_path=str(tmp_path / "jobs.sqlite"))


def _await_status(store, jid, *, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        cur = store.get(jid)
        if cur.status in ("done", "error"):
            return cur
        time.sleep(0.05)
    return store.get(jid)


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


def test_run_async_failed_job_records_error_and_redacts_traceback(tmp_path):
    """The except branch (the common production outcome) must flip to 'error', keep a short message,
    and NOT leak a raw traceback (absolute paths / 'Traceback (most recent call last)') over the API."""
    src = tmp_path / "in.bin"
    src.write_bytes(b"\x00\x01 not a real document \xff\xfe")
    s = _store(tmp_path)
    job = s.create(str(src), meta={"filename": "in.bin"})
    # an engine pointed at a real model with a junk binary input -> the pipeline raises; but to keep
    # the test fast/offline, force a raise by handing run() an unreadable path via a bad output dir.
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.MARKDOWN)
    job.input_path = str(tmp_path / "does-not-exist.txt")   # extract will fail -> except branch
    s.run_async(job, cfg)

    final = _await_status(s, job.id)
    assert final.status == "error"
    assert final.error and "Traceback (most recent call last)" not in final.error
    assert "\n" not in (final.message or "")          # one-line client message, no stack
    assert final.progress < 1.0


def test_run_lock_serialises_jobs(tmp_path):
    """The single-box OOM-prevention invariant: two jobs never execute concurrently. Instrument a
    stub that records max overlap while holding the run lock."""
    s = _store(tmp_path)
    active = {"now": 0, "max": 0}
    lk = threading.Lock()

    def fake_run_locked(job, cfg):
        with lk:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.2)
        with lk:
            active["now"] -= 1
        job.status = "done"
        s._save(job)

    s._run_locked = fake_run_locked            # type: ignore[method-assign]
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.MARKDOWN)
    jobs_list = [s.create(f"in{i}.txt", meta={}) for i in range(3)]
    for j in jobs_list:
        s.run_async(j, cfg)
    for j in jobs_list:
        _await_status(s, j.id)
    assert active["max"] == 1, "jobs ran concurrently — _RUN_LOCK not serialising"
