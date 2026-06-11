"""FastAPI app: upload -> async translate job -> poll -> download. Serves the web UI."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

from ..config import (Config, Engine, Fidelity, OutputFormat, Register)
from .jobs import store

app = FastAPI(title="transdoc", description="Document Intelligence & Translation")

_WEB = Path(__file__).parent / "web"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    idx = _WEB / "index.html"
    return idx.read_text(encoding="utf-8") if idx.exists() else "<h1>transdoc</h1>"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "engines": [e.value for e in Engine],
            "formats": [f.value for f in OutputFormat]}


@app.post("/api/translate")
async def translate(
    file: UploadFile = File(...),
    target_lang: str = Form(...),
    source_lang: str = Form("auto"),
    output_format: str = Form("docx"),
    engine: str = Form("fallback"),
    fidelity: str = Form("auto"),
    domain: str = Form("auto"),
    register: str = Form("auto"),
) -> dict:
    # save upload to a temp file
    suffix = Path(file.filename or "doc").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with tmp as f:
        shutil.copyfileobj(file.file, f)

    try:
        cfg = Config(
            source_lang=source_lang,
            target_lang=target_lang,
            output_format=OutputFormat(output_format),
            engine=Engine(engine),
            fidelity=Fidelity(fidelity),
            domain=domain,
            register=Register(register),
        )
    except ValueError as e:
        raise HTTPException(400, f"bad config: {e}")

    job = store.create(tmp.name, meta={"filename": file.filename})
    store.run_async(job, cfg)
    return {"job_id": job.id, "status": job.status}


@app.get("/api/jobs/{jid}")
def job_status(jid: str) -> dict:
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    return {
        "job_id": job.id, "status": job.status, "progress": job.progress,
        "message": job.message, "error": job.error, "meta": job.meta,
        "has_output": bool(job.output_path), "has_report": bool(job.report_path),
    }


@app.get("/api/download/{jid}")
def download(jid: str):
    job = store.get(jid)
    if not job or not job.output_path:
        raise HTTPException(404, "output not ready")
    name = f"{Path(job.meta.get('filename', 'document')).stem}.{job.id}{Path(job.output_path).suffix}"
    return FileResponse(job.output_path, filename=name)


@app.get("/api/report/{jid}")
def report(jid: str):
    job = store.get(jid)
    if not job or not job.report_path:
        raise HTTPException(404, "report not ready")
    return FileResponse(job.report_path, filename=f"report.{job.id}.md")
