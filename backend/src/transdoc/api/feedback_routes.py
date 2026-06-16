"""REST feedback API (PR-5): a thin HTTP surface over the glossary / TM / correction stores so the
web review UI (PR-6) is a thin client. Mirrors the `transdoc glossary|correct|tm` CLI verbs.

Localhost-trust, no auth — consistent with the rest of the local app (bind 127.0.0.1). Every write
goes through the same store methods the CLI uses, so behaviour (precedence, confirmed-immunity,
suggestion promotion) is identical across surfaces.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..store.glossary import GlossaryStore
from ..store.tm import TMStore

router = APIRouter(prefix="/api")


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
