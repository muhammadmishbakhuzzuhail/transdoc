# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""FastAPI app: upload -> async translate job -> poll -> download. Serves the web UI."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from ..config import Config, Engine, Fidelity, OCREngine, OutputFormat, Register
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

_WEB = Path(__file__).parent / "web"      # committed self-contained fallback UI (single index.html)
_SPA = Path(__file__).parent / "spa"      # built React app (gitignored; `make build-web` / Docker)

# Serve the React SPA's hashed assets when a build is present. Without one (plain `python
# server.py`), the fallback web/index.html is served and there are no assets to mount.
if (_SPA / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_SPA / "assets"), name="assets")


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    # prefer the built React SPA; fall back to the bundled single-file UI
    for idx in (_SPA / "index.html", _WEB / "index.html"):
        if idx.exists():
            return idx.read_text(encoding="utf-8")
    return "<h1>transdoc</h1>"


@app.get("/api/health")
def health() -> dict:
    from .. import __version__
    from ..translate.suggest import STYLE_DIRECTIVES
    return {"status": "ok",
            "version": __version__,
            "engines": [e.value for e in Engine],
            "formats": [f.value for f in OutputFormat],
            "fidelity": [f.value for f in Fidelity],
            "ocr": [o.value for o in OCREngine],
            "register": [r.value for r in Register],
            "layout": ["auto", "off", "paddle"],
            "styles": list(STYLE_DIRECTIVES)}   # rephrase / alternatives mode presets (review UI)


def _make_cfg(*, target_lang, source_lang, output_format, engine, fidelity, domain, register,
              layout, ocr_engine, bilingual, quality, localize, pages, align=True,
              repair=False, escalate=False, verify=False, reading_order="xycut",
              engines="") -> Config:
    """Build a Config from the upload form, raising HTTP 400 on a bad value. A fresh Config per
    job — the pipeline mutates cfg.fidelity/layout for some inputs, so jobs must not share one."""
    try:
        candidates = [Engine(e.strip()) for e in (engines or "").split(",") if e.strip()]
        return Config(
            source_lang=source_lang, target_lang=target_lang,
            output_format=OutputFormat(output_format), engine=Engine(engine),
            engine_candidates=candidates,
            fidelity=Fidelity(fidelity), domain=domain, register=Register(register),
            ocr_engine=OCREngine(ocr_engine), layout=layout, bilingual=bilingual,
            quality_check=quality, localize=localize, pages=pages or None,
            align_styles=align, repair=repair, escalate=escalate, verify=verify,
            reading_order_engine=reading_order,
        )
    except ValueError as e:
        raise HTTPException(400, f"bad config: {e}")


def _save_upload(file: UploadFile) -> str:
    """Persist an upload to a temp file, rejecting oversized inputs (HTTP 413). Returns the path.
    Streams with a hard byte cap so an oversized/zip-bomb upload can't fill the disk before the
    size check (the old code copied the whole file first, then checked)."""
    from ..limits import MAX_FILE_MB, InputTooLarge, check_zip_bomb
    cap = MAX_FILE_MB * 1024 * 1024
    suffix = Path(file.filename or "doc").suffix or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    written = 0
    try:
        with tmp as f:
            while chunk := file.file.read(1024 * 1024):
                written += len(chunk)
                if written > cap:
                    raise HTTPException(413, f"file exceeds the {MAX_FILE_MB} MB limit")
                f.write(chunk)
        # zip-bomb guard on the synchronous upload path too (office/EPUB are zip containers)
        if suffix.lower() in (".docx", ".xlsx", ".pptx", ".epub", ".odt", ".zip"):
            try:
                check_zip_bomb(tmp.name)
            except InputTooLarge as e:
                raise HTTPException(413, str(e))
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
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
    align: bool = Form(True),
    repair: bool = Form(False),
    escalate: bool = Form(False),
    verify: bool = Form(False),
    reading_order: str = Form("xycut"),
    engines: str = Form(""),
    pages: str = Form(""),
) -> dict:
    path = _save_upload(file)
    cfg = _make_cfg(target_lang=target_lang, source_lang=source_lang, output_format=output_format,
                    engine=engine, fidelity=fidelity, domain=domain, register=register,
                    layout=layout, ocr_engine=ocr_engine, bilingual=bilingual, quality=quality,
                    localize=localize, align=align, repair=repair, escalate=escalate,
                    verify=verify, reading_order=reading_order, engines=engines, pages=pages)
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
    align: bool = Form(True),
    repair: bool = Form(False),
    escalate: bool = Form(False),
    verify: bool = Form(False),
    reading_order: str = Form("xycut"),
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
                        bilingual=bilingual, quality=quality, localize=localize, align=align,
                        repair=repair, escalate=escalate, verify=verify,
                        reading_order=reading_order, pages=pages)
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
