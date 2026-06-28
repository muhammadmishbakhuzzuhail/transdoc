# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""REST feedback API (PR-5): a thin HTTP surface over the glossary / TM / correction stores so the
web review UI (PR-6) is a thin client. Mirrors the `transdoc glossary|correct|tm` CLI verbs.

Localhost-trust, no auth — consistent with the rest of the local app (bind 127.0.0.1). Every write
goes through the same store methods the CLI uses, so behaviour (precedence, confirmed-immunity,
suggestion promotion) is identical across surfaces.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

from ..store.glossary import GlossaryStore
from ..store.tm import TMStore

router = APIRouter(prefix="/api")


async def _save_capped(file: UploadFile, suffix: str) -> str:
    """Stream an upload to a temp file with a hard byte cap (HTTP 413), like app._save_upload.
    The CSV/TMX import endpoints previously did `await file.read()` with no limit -> a large upload
    could exhaust memory."""
    from ..limits import MAX_FILE_MB
    cap = MAX_FILE_MB * 1024 * 1024
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    written = 0
    try:
        with tmp as f:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > cap:
                    raise HTTPException(413, f"file exceeds the {MAX_FILE_MB} MB limit")
                f.write(chunk)
    except Exception:
        Path(tmp.name).unlink(missing_ok=True)
        raise
    return tmp.name


def _glossary() -> GlossaryStore:
    gs = GlossaryStore.get()
    if gs is None:
        raise HTTPException(503, "glossary store unavailable (persistence disabled)")
    return gs


def _tm() -> TMStore:
    tm = TMStore.get()
    if tm is None:
        raise HTTPException(503, "translation memory unavailable (persistence disabled)")
    return tm


# --- glossary ---------------------------------------------------------------------------------

class GlossaryAdd(BaseModel):
    term: str
    rendering: str
    src_lang: str
    tgt_lang: str
    domain: str = ""
    locked: bool = False


class GlossaryRemove(BaseModel):
    term: str
    src_lang: str
    tgt_lang: str
    domain: str = ""


@router.get("/glossary")
def glossary_list(src_lang: str | None = None, tgt_lang: str | None = None,
                  domain: str | None = None) -> dict:
    return {"entries": _glossary().list(src_lang, tgt_lang, domain)}


@router.post("/glossary")
def glossary_add(body: GlossaryAdd) -> dict:
    _glossary().add(body.term, body.rendering, body.src_lang, body.tgt_lang,
                    domain=body.domain, locked=body.locked)
    return {"ok": True}


@router.delete("/glossary")
def glossary_remove(body: GlossaryRemove) -> dict:
    n = _glossary().remove(body.term, body.src_lang, body.tgt_lang, domain=body.domain)
    return {"removed": n}


# --- suggestions ------------------------------------------------------------------------------

class SuggestionAccept(BaseModel):
    term: str
    src_lang: str
    tgt_lang: str
    domain: str = ""
    locked: bool = False


@router.get("/glossary/suggestions")
def suggestions_list(src_lang: str | None = None, tgt_lang: str | None = None,
                     domain: str | None = None) -> dict:
    return {"suggestions": _glossary().list_suggestions(src_lang, tgt_lang, domain)}


@router.post("/glossary/suggestions/accept")
def suggestions_accept(body: SuggestionAccept) -> dict:
    ok = _glossary().accept_suggestion(body.term, body.src_lang, body.tgt_lang,
                                       domain=body.domain, locked=body.locked)
    if not ok:
        raise HTTPException(404, "no such suggestion")
    return {"ok": True}


# --- corrections ------------------------------------------------------------------------------

class Correction(BaseModel):
    source: str
    fix: str
    src_lang: str
    tgt_lang: str
    domain: str = ""
    term: bool = False          # True -> glossary (authoritative); False -> confirmed TM segment
    locked: bool = False


@router.post("/correct")
def correct(body: Correction) -> dict:
    from ..store.feedback import record_correction
    ok = record_correction(body.source, body.fix, body.src_lang, body.tgt_lang,
                           domain=body.domain, scope="term" if body.term else "segment",
                           locked=body.locked)
    if not ok:
        raise HTTPException(400, "correction not recorded (empty input or store unavailable)")
    return {"ok": True, "scope": "term" if body.term else "segment"}


# --- translation memory -----------------------------------------------------------------------

class TMConfirm(BaseModel):
    source: str
    tgt_lang: str
    src_lang: str = ""
    domain: str = ""


class TMPurge(BaseModel):
    unconfirmed_only: bool = True
    older_than_days: int | None = None


@router.get("/tm/stats")
def tm_stats() -> dict:
    return _tm().stats()


@router.post("/tm/confirm")
def tm_confirm(body: TMConfirm) -> dict:
    n = _tm().confirm(body.source, body.tgt_lang, src_lang=body.src_lang, domain=body.domain)
    return {"confirmed": n}


@router.post("/tm/purge")
def tm_purge(body: TMPurge) -> dict:
    n = _tm().purge(unconfirmed_only=body.unconfirmed_only, older_than_days=body.older_than_days)
    return {"purged": n}


# --- interchange: TMX (TM) + CSV (glossary) export/import -------------------------------------

@router.get("/glossary/export.csv")
def glossary_export_csv(src_lang: str | None = None, tgt_lang: str | None = None):
    from ..store.interchange import export_glossary_csv
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    tmp.close()
    export_glossary_csv(_glossary(), tmp.name, src_lang, tgt_lang)
    return FileResponse(tmp.name, filename="glossary.csv", media_type="text/csv",
                        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True))


@router.post("/glossary/import")
async def glossary_import(file: UploadFile = File(...), src_lang: str = Form(""),
                          tgt_lang: str = Form(""), domain: str = Form("")) -> dict:
    from ..store.interchange import import_glossary_csv
    name = await _save_capped(file, ".csv")
    try:
        n = import_glossary_csv(_glossary(), name, src_lang, tgt_lang, domain)
    finally:
        Path(name).unlink(missing_ok=True)
    return {"imported": n}


@router.get("/tm/export.tmx")
def tm_export_tmx():
    from ..store.interchange import export_tmx
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".tmx")
    tmp.close()
    export_tmx(_tm(), tmp.name)
    return FileResponse(tmp.name, filename="tm.tmx", media_type="application/x-tmx+xml",
                        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True))


@router.post("/tm/import")
async def tm_import(file: UploadFile = File(...)) -> dict:
    from ..store.interchange import import_tmx
    name = await _save_capped(file, ".tmx")
    try:
        n = import_tmx(_tm(), name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"bad TMX: {e}")
    finally:
        Path(name).unlink(missing_ok=True)
    return {"imported": n}


# --- LLM alternative translations (review aid) ------------------------------------------------

class AltReq(BaseModel):
    source: str
    src_lang: str = ""
    tgt_lang: str
    domain: str = ""
    n: int = 3
    style: str = ""                   # optional mode preset (general|professional|academic|...)


@router.post("/alternatives")
def alternatives(body: AltReq) -> dict:
    """Generate alternative translations of one segment via the local LLM (Gemma/Ollama). 503 if the
    local LLM isn't reachable — the UI hides the feature then."""
    from ..config import Config, Register
    from ..translate.ollama import OllamaError, OllamaTranslator
    if not body.source.strip():
        return {"alternatives": []}
    cfg = Config(source_lang=body.src_lang or "auto", target_lang=body.tgt_lang,
                 domain=body.domain or "auto", register=Register("auto"))
    try:
        # same GPU lock as /synonyms and /rephrase — Ollama loads the local LLM onto the same 6 GB
        # card a translate job uses; serialise against in-flight jobs instead of racing into OOM.
        alts = _with_gpu_lock(lambda: OllamaTranslator().alternatives(
            body.source, cfg, src=body.src_lang or None, n=body.n, style=body.style or None))
    except OllamaError as e:
        raise HTTPException(503, f"local LLM unavailable: {e}")
    return {"alternatives": alts}


# --- review suggestion layer: in-context synonyms + sentence rephrase (Grammarly-style assist) ---

class SynReq(BaseModel):
    phrase: str                       # the selected word/phrase (already translated)
    context: str = ""                 # the full translated sentence it sits in
    tgt_lang: str
    n: int = 6


class RephraseReq(BaseModel):
    sentence: str                     # the translated sentence to rewrite
    tgt_lang: str
    style: str = "general"            # general|professional|academic|friendly|concise
    n: int = 3


def _suggest_cfg(tgt_lang: str):
    from ..config import Config, Register
    return Config(source_lang="auto", target_lang=tgt_lang, register=Register("auto"))


# The review LLM (Qwen) loads ~2.5-3 GB of GPU. A translate job loads paddle/COMET/ollama on the
# same 6 GB card. They must never co-reside, so the suggestion endpoints take the same lock that
# serialises job execution — a review request simply waits for any in-flight job rather than racing
# it into a CUDA OOM. (The job pipeline also Suggester.release()s at its start.)
def _with_gpu_lock(fn):
    from .jobs import _RUN_LOCK
    with _RUN_LOCK:
        return fn()


@router.post("/synonyms")
def synonyms(body: SynReq) -> dict:
    """In-context alternatives for a selected phrase within a translated sentence (local LLM).
    503 when the suggestion model isn't installed/loadable — the UI hides the feature then."""
    from ..translate.suggest import Suggester, SuggestError
    if not body.phrase.strip():
        return {"synonyms": []}
    try:
        out = _with_gpu_lock(lambda: Suggester().synonyms(
            body.phrase, body.context, _suggest_cfg(body.tgt_lang), n=body.n))
    except SuggestError as e:
        raise HTTPException(503, f"suggestion model unavailable: {e}")
    return {"synonyms": out}


@router.post("/rephrase")
def rephrase(body: RephraseReq) -> dict:
    """Rewrite a translated sentence in the requested style/mode (local LLM). 503 if unavailable."""
    from ..translate.suggest import Suggester, SuggestError
    if not body.sentence.strip():
        return {"rephrasings": []}
    try:
        out = _with_gpu_lock(lambda: Suggester().rephrase(
            body.sentence, _suggest_cfg(body.tgt_lang), style=body.style, n=body.n))
    except SuggestError as e:
        raise HTTPException(503, f"suggestion model unavailable: {e}")
    return {"rephrasings": out}


# --- per-job review payload (side-by-side UI) -------------------------------------------------

@router.get("/review/{jid}")
def review(jid: str) -> dict:
    """The translated segments + run suggestions for the side-by-side review UI. Read from the
    ``review.json`` the job worker wrote on completion."""
    from .jobs import store
    job = store.get(jid)
    if not job:
        raise HTTPException(404, "job not found")
    if not job.output_path:
        raise HTTPException(404, "review not ready")
    path = Path(job.output_path).parent / "review.json"
    if not path.exists():
        raise HTTPException(404, "review not available")
    return json.loads(path.read_text(encoding="utf-8"))
