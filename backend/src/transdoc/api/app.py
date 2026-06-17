"""FastAPI app: upload -> async translate job -> poll -> download. Serves the web UI."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from ..config import (Config, Engine, Fidelity, OCREngine, OutputFormat, Register)
from .feedback_routes import router as feedback_router
from .jobs import store

app = FastAPI(title="transdoc", description="Document Intelligence & Translation")
app.include_router(feedback_router)

# The React dev server (Vite, :5173) and any deployed origin call this API cross-origin.
# Override with TRANSDOC_CORS_ORIGINS="https://app.example.com,https://..." in production.
_origins = os.environ.get(
    "TRANSDOC_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

_WEB = Path(__file__).parent / "web"


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    idx = _WEB / "index.html"
    return idx.read_text(encoding="utf-8") if idx.exists() else "<h1>transdoc</h1>"


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok",
            "engines": [e.value for e in Engine],
            "formats": [f.value for f in OutputFormat],
            "fidelity": [f.value for f in Fidelity],
            "ocr": [o.value for o in OCREngine],
            "register": [r.value for r in Register],
            "layout": ["auto", "off", "paddle"]}


def _make_cfg(*, target_lang, source_lang, output_format, engine, fidelity, domain, register,
              layout, ocr_engine, bilingual, quality, localize, pages) -> Config:
    """Build a Config from the upload form, raising HTTP 400 on a bad value. A fresh Config per
    job — the pipeline mutates cfg.fidelity/layout for some inputs, so jobs must not share one."""
    try:
        return Config(
            source_lang=source_lang, target_lang=target_lang,
            output_format=OutputFormat(output_format), engine=Engine(engine),
            fidelity=Fidelity(fidelity), domain=domain, register=Register(register),
            ocr_engine=OCREngine(ocr_engine), layout=layout, bilingual=bilingual,
            quality_check=quality, localize=localize, pages=pages or None,
        )
    except ValueError as e:
        raise HTTPException(400, f"bad config: {e}")


def _save_upload(file: UploadFile) -> str:
    """Persist an upload to a temp file, rejecting oversized inputs (HTTP 413). Returns the path."""
    suffix = Path(file.filename or "doc").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    with tmp as f:
        shutil.copyfileobj(file.file, f)
    from ..limits import InputTooLarge, check_file_size
    try:
        check_file_size(tmp.name)
    except InputTooLarge as e:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(413, str(e))
    return tmp.name


@app.post("/api/translate")
async def translate(
    file: UploadFile = File(...),
    target_lang: str = Form(...),
    source_lang: str = Form("auto"),
    output_format: str = Form("docx"),
    engine: str = Form("google"),
    fidelity: str = Form("auto"),
    domain: str = Form("auto"),
    register: str = Form("auto"),
    layout: str = Form("auto"),
    ocr_engine: str = Form("auto"),
    bilingual: bool = Form(False),
    quality: bool = Form(True),
    localize: bool = Form(False),
    pages: str = Form(""),
) -> dict:
    path = _save_upload(file)
    cfg = _make_cfg(target_lang=target_lang, source_lang=source_lang, output_format=output_format,
                    engine=engine, fidelity=fidelity, domain=domain, register=register,
                    layout=layout, ocr_engine=ocr_engine, bilingual=bilingual, quality=quality,
                    localize=localize, pages=pages)
    job = store.create(path, meta={"filename": file.filename})
    store.run_async(job, cfg)
    return {"job_id": job.id, "status": job.status}


@app.post("/api/batch")
async def batch(
    files: list[UploadFile] = File(...),
    target_lang: str = Form(...),
    source_lang: str = Form("auto"),
    output_format: str = Form("docx"),
    engine: str = Form("google"),
    fidelity: str = Form("auto"),
    domain: str = Form("auto"),
    register: str = Form("auto"),
    layout: str = Form("auto"),
    ocr_engine: str = Form("auto"),
    bilingual: bool = Form(False),
    quality: bool = Form(True),
    localize: bool = Form(False),
    pages: str = Form(""),
) -> dict:
    """Batch upload: one independent job per file (DeepL-style), tied by a shared batch_id, applied
    with the SAME settings. Heavy work is serialised by the job store, so they run one at a time."""
    if not files:
        raise HTTPException(400, "no files")
    bid = uuid.uuid4().hex[:12]
    out = []
    for file in files:
        path = _save_upload(file)
        cfg = _make_cfg(target_lang=target_lang, source_lang=source_lang,
                        output_format=output_format, engine=engine, fidelity=fidelity,
                        domain=domain, register=register, layout=layout, ocr_engine=ocr_engine,
                        bilingual=bilingual, quality=quality, localize=localize, pages=pages)
        job = store.create(path, meta={"filename": file.filename}, batch_id=bid)
        store.run_async(job, cfg)
        out.append({"job_id": job.id, "filename": file.filename})
    return {"batch_id": bid, "jobs": out}


@app.get("/api/batch/{bid}")
def batch_status(bid: str) -> dict:
    jobs = store.list_batch(bid)
    if not jobs:
        raise HTTPException(404, "batch not found")
    return {"batch_id": bid, "jobs": [
        {"job_id": j.id, "filename": j.meta.get("filename", ""), "status": j.status,
         "progress": j.progress, "message": j.message, "error": j.error,
         "has_output": bool(j.output_path), "has_report": bool(j.report_path)}
        for j in jobs]}


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


def _job_file(jid: str, which: str) -> str:
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    path = job.input_path if which == "source" else job.output_path
    if which not in ("source", "output") or not path:
        raise HTTPException(404, "not available")
    return path


@app.get("/api/preview/{jid}/info")
def preview_info(jid: str) -> dict:
    """Page counts + previewability for source and output, so the UI can render a
    side-by-side image preview. A file PyMuPDF can't rasterise (e.g. .docx, .txt) is
    reported ok=False and the UI falls back to a download link."""
    import fitz

    def probe(which: str) -> dict:
        try:
            path = _job_file(jid, which)
        except HTTPException:
            return {"ok": False, "pages": 0}
        try:
            doc = fitz.open(path)
            n = doc.page_count
            doc.close()
            return {"ok": n > 0, "pages": n}
        except Exception:
            return {"ok": False, "pages": 0}

    return {"source": probe("source"), "output": probe("output")}


@app.get("/api/preview/{jid}/{which}/{page}.png")
def preview_page(jid: str, which: str, page: int):
    """Rasterise one page of the source or output document to PNG (~110 dpi)."""
    import fitz

    path = _job_file(jid, which)
    try:
        doc = fitz.open(path)
    except Exception:
        raise HTTPException(415, "not previewable")
    try:
        if page < 0 or page >= doc.page_count:
            raise HTTPException(404, "page out of range")
        png = doc[page].get_pixmap(dpi=110).tobytes("png")
    finally:
        doc.close()
    return Response(png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/analysis/{jid}")
def analysis(jid: str):
    """Full analysis JSON for the UI: profile, flagged items, glossary, repairs, regions."""
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    path = Path(store.work_dir) / jid / "analysis.json"
    if not path.exists():
        raise HTTPException(404, "analysis not ready")
    return JSONResponse(json.loads(path.read_text()))
