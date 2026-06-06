"""In-process async job store. No external queue needed for a single-node deployment;
swap for Celery/Redis later via the same interface.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
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


class JobStore:
    def __init__(self, work_dir: str = "/tmp/transdoc_jobs"):
        self.jobs: dict[str, Job] = {}
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, input_path: str, meta: dict) -> Job:
        jid = uuid.uuid4().hex[:12]
        job = Job(id=jid, input_path=input_path, meta=meta)
        with self._lock:
            self.jobs[jid] = job
        return job

    def get(self, jid: str) -> Optional[Job]:
        return self.jobs.get(jid)

    def run_async(self, job: Job, cfg: Config) -> None:
        t = threading.Thread(target=self._run, args=(job, cfg), daemon=True)
        t.start()

    def _run(self, job: Job, cfg: Config) -> None:
        job.status = "running"
        job.progress = 0.1
        job.message = "extracting + diagnosing"
        try:
            out_dir = self.work_dir / job.id
            out_dir.mkdir(exist_ok=True)
            ext = {"markdown": ".md", "docx": ".docx", "pdf": ".pdf",
                   "plain-text": ".txt"}.get(cfg.output_format.value, ".md")
            out_path = str(out_dir / f"translated{ext}")
            job.progress = 0.3
            job.message = "translating"
            res = run(job.input_path, cfg, out_path)
            job.output_path = res.output_path
            job.report_path = res.report_path
            job.meta["blocks"] = len(res.doc.blocks)
            job.meta["flagged"] = len(res.doc.flagged_blocks())
            job.meta["pages"] = res.doc.page_count
            job.progress = 1.0
            job.status = "done"
            job.message = "completed"
        except Exception as e:
            job.status = "error"
            job.error = f"{e}\n{traceback.format_exc()}"
            job.message = str(e)


store = JobStore()
