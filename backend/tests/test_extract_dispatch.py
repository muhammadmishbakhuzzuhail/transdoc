"""Scan routing: a non-Latin scanned PDF goes to the digital line-OCR extractor (better non-Latin
OCR), a Latin scan keeps the PP-StructureV3 structured path."""

from __future__ import annotations

from pathlib import Path

import pytest

from transdoc.config import Config
from transdoc.extract import _is_non_latin_source, extract
from transdoc.ingest.detect import Detection, Kind
from transdoc.ir import Document


def test_is_non_latin_source():
    assert _is_non_latin_source(Config(target_lang="id", source_lang="hi"))
    assert _is_non_latin_source(Config(target_lang="id", source_lang="zh"))
    assert _is_non_latin_source(Config(target_lang="id", source_lang="ar"))
    assert not _is_non_latin_source(Config(target_lang="id", source_lang="en"))
    assert not _is_non_latin_source(Config(target_lang="id", source_lang="auto"))


def _route(monkeypatch, source_lang, kind=Kind.PDF_SCAN):
    """Dispatch a PDF of the given kind+source and report which extractor ran."""
    pdf = Path("corpus/real/scanned_pdf/udhr_hindi_scan.pdf")
    if not pdf.exists():
        pytest.skip("corpus scan not present")
    monkeypatch.delenv("TRANSDOC_LAYOUT_DISABLE", raising=False)
    called = {"who": None}

    def _struct(p, cfg):
        called["who"] = "structured"
        return Document(source_path=str(p), mime="application/pdf")

    def _digital(p, cfg, **kw):
        called["who"] = "digital"
        return Document(source_path=str(p), mime="application/pdf")

    import transdoc.extract.pdf as pdf_mod
    import transdoc.extract.structured as struct_mod
    monkeypatch.setattr(struct_mod, "extract_structured", _struct)
    monkeypatch.setattr(pdf_mod, "extract", _digital)

    det = Detection(kind=kind, mime="application/pdf", path=pdf, notes="")
    extract(det, Config(target_lang="id", source_lang=source_lang, layout="paddle"))
    return called["who"]


def test_non_latin_scan_routes_to_digital(monkeypatch):
    assert _route(monkeypatch, "hi") == "digital"


def test_non_latin_digital_routes_to_digital(monkeypatch):
    # a non-Latin DIGITAL PDF also skips PP-StructureV3 (its non-Latin re-OCR mangles the clean
    # text layer — e.g. Arabic came out as disconnected letters).
    assert _route(monkeypatch, "ar", kind=Kind.PDF_DIGITAL) == "digital"


def test_latin_digital_keeps_structured(monkeypatch):
    assert _route(monkeypatch, "en", kind=Kind.PDF_DIGITAL) == "structured"


def test_latin_scan_keeps_structured(monkeypatch):
    assert _route(monkeypatch, "en") == "structured"
