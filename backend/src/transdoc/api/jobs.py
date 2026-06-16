"""Async job store with SQLite persistence.

Jobs survive a server restart and are visible across processes/uvicorn workers: the SQLite
row is the source of truth, the in-memory ``Job`` is a working copy the worker thread mutates
and flushes after every state change. On startup any job still marked ``queued``/``running``
(its worker thread died with the old process) is recovered to ``error`` so clients stop
polling a job that will never finish.

The work itself still runs in an in-process daemon thread — fine for a single node. To scale
to multiple worker processes, swap ``run_async`` for a Celery task enqueue; the persisted
store and HTTP surface stay identical.

Env:
  TRANSDOC_JOBS_DB    SQLite path (default: <work_dir>/jobs.sqlite)
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Optional

from ..config import Config
from ..pipeline import run


@dataclass
class Job:
    id: str
    status: str = "queued"          # queued|running|done|error
    progress: float = 0.0           # 0..1
    message: str = ""
    input_path: str = ""
    output_path: Optional[str] = None
    report_path: Optional[str] = None
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)
    updated_at: float = 0.0
    batch_id: Optional[str] = None  # set when the job is part of a batch upload


# Heavy translation work (OCR + local LLM) is memory-hungry; on a single CPU box two jobs at once
# risk OOM. Serialise the actual run so jobs queue instead of competing — a job waits here as
# 'queued' and flips to 'running' only once it holds the lock.
_RUN_LOCK = threading.Lock()


_COLUMNS = [f.name for f in fields(Job)]


class JobStore:
    def __init__(self, work_dir: str = "/tmp/transdoc_jobs", db_path: str | None = None):
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        db = db_path or os.environ.get("TRANSDOC_JOBS_DB") or str(self.work_dir / "jobs.sqlite")
        self._conn = sqlite3.connect(db, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS jobs (
                   id TEXT PRIMARY KEY,
                   status TEXT NOT NULL,
                   progress REAL NOT NULL,
                   message TEXT,
                   input_path TEXT,
                   output_path TEXT,
                   report_path TEXT,
                   error TEXT,
                   meta TEXT,
                   updated_at REAL
               )"""
        )
        # batch_id was added later; add the column to pre-existing DBs (ignored if present)
        try:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN batch_id TEXT")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass
        self._conn.commit()
        self._recover_orphans()

    def _recover_orphans(self) -> None:
        """A job left 'queued'/'running' means its worker thread died with the old process."""
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status='error', message='interrupted by restart', "
                "error='interrupted by restart', updated_at=? "
                "WHERE status IN ('queued','running')",
                (time.time(),),
            )
            self._conn.commit()

    def _save(self, job: Job) -> None:
        job.updated_at = time.time()
        row = asdict(job)
        row["meta"] = json.dumps(row["meta"])
        with self._lock:
            placeholders = ",".join("?" * len(_COLUMNS))
            self._conn.execute(
                f"INSERT OR REPLACE INTO jobs ({','.join(_COLUMNS)}) VALUES ({placeholders})",
                [row[c] for c in _COLUMNS],
            )
            self._conn.commit()

    def create(self, input_path: str, meta: dict, batch_id: str | None = None) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(id=jid, input_path=input_path, meta=meta, batch_id=batch_id)
        self._save(job)
        return job

    def list_batch(self, batch_id: str) -> list[Job]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM jobs WHERE batch_id=? ORDER BY updated_at", (batch_id,))
            rows = cur.fetchall()
        out = []
        for r in rows:
            data = dict(r)
            data["meta"] = json.loads(data["meta"]) if data["meta"] else {}
            out.append(Job(**{c: data[c] for c in _COLUMNS}))
        return out

    def get(self, jid: str) -> Optional[Job]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM jobs WHERE id=?", (jid,))
            r = cur.fetchone()
        if r is None:
            return None
        data = dict(r)
        data["meta"] = json.loads(data["meta"]) if data["meta"] else {}
        return Job(**{c: data[c] for c in _COLUMNS})

    def run_async(self, job: Job, cfg: Config) -> None:
        t = threading.Thread(target=self._run, args=(job, cfg), daemon=True)
        t.start()

    def _run(self, job: Job, cfg: Config) -> None:
        # block here until no other job is running (serialise heavy work); stay 'queued' meanwhile
        with _RUN_LOCK:
            self._run_locked(job, cfg)

    def _run_locked(self, job: Job, cfg: Config) -> None:
        job.status = "running"
        job.progress = 0.1
        job.message = "extracting + diagnosing"
        self._save(job)
        try:
            out_dir = self.work_dir / job.id
            out_dir.mkdir(exist_ok=True)
            ext = {"markdown": ".md", "docx": ".docx", "pdf": ".pdf",
                   "plain-text": ".txt"}.get(cfg.output_format.value, ".md")
            out_path = str(out_dir / f"translated{ext}")
            job.progress = 0.3
            job.message = "translating"
            self._save(job)
            res = run(job.input_path, cfg, out_path)
            job.output_path = res.output_path
            job.report_path = res.report_path
            job.meta["blocks"] = len(res.doc.blocks)
            job.meta["flagged"] = len(res.doc.flagged_blocks())
            job.meta["pages"] = res.doc.page_count
            # full analysis for the UI (profile, flagged, glossary, repairs, regions)
            try:
                from .analysis import build_analysis
                (out_dir / "analysis.json").write_text(
                    json.dumps(build_analysis(res.doc, cfg)))
            except Exception:  # analysis is best-effort, never fail the job over it
                pass
            try:
                from .review import build_review
                (out_dir / "review.json").write_text(
                    json.dumps(build_review(res.doc), ensure_ascii=False))
            except Exception:  # review payload is best-effort too
                pass
            job.progress = 1.0
            job.status = "done"
            job.message = "completed"
        except Exception as e:
            job.status = "error"
            job.error = f"{e}\n{traceback.format_exc()}"
            job.message = str(e)
        self._save(job)


store = JobStore()
