# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Auto source on a scan/image resolves the OCR language from the page script (OSD), so a
non-Latin scan picks the right model instead of a Latin/Chinese default that yields garbage."""

from __future__ import annotations

import types

from transdoc import pipeline
from transdoc.ingest.detect import Kind


def _det(kind, path):
    return types.SimpleNamespace(kind=kind, path=str(path))


def test_non_scan_returns_none():
    # a digital/office input is never OSD-probed
    assert pipeline._autosource_script(_det(Kind.DOCX, "x.docx")) is None


def test_scan_maps_script_to_lang(tmp_path, monkeypatch):
    f = tmp_path / "scan.png"
    f.write_bytes(b"not-a-real-image")            # content irrelevant; detect_script is stubbed
    monkeypatch.setattr("transdoc.ocr.router.detect_script", lambda img: "Devanagari")
    assert pipeline._autosource_script(_det(Kind.IMAGE, f)) == "hi"
    monkeypatch.setattr("transdoc.ocr.router.detect_script", lambda img: "Arabic")
    assert pipeline._autosource_script(_det(Kind.IMAGE, f)) == "ar"


def test_latin_or_unknown_stays_none(tmp_path, monkeypatch):
    f = tmp_path / "scan.png"
    f.write_bytes(b"x")
    monkeypatch.setattr("transdoc.ocr.router.detect_script", lambda img: "Latin")
    assert pipeline._autosource_script(_det(Kind.IMAGE, f)) is None
    monkeypatch.setattr("transdoc.ocr.router.detect_script", lambda img: None)
    assert pipeline._autosource_script(_det(Kind.IMAGE, f)) is None


def test_indic_scripts_resolve(tmp_path, monkeypatch):
    # Kannada + the Tesseract-only Indic scripts must resolve so an auto-source scan routes to the
    # right OCR model instead of the English structured default.
    f = tmp_path / "scan.png"
    f.write_bytes(b"x")
    for script, lang in [("Kannada", "kn"), ("Malayalam", "ml"), ("Gujarati", "gu"),
                         ("Gurmukhi", "pa"), ("Oriya", "or"), ("Sinhala", "si")]:
        monkeypatch.setattr("transdoc.ocr.router.detect_script", lambda img, s=script: s)
        assert pipeline._autosource_script(_det(Kind.IMAGE, f)) == lang


def test_indic_lang_to_script_routes_paddle_or_tess():
    # explicit --source for these scripts must map to a script so the non-Latin dispatch + chain fire
    from transdoc.ocr.router import LANG_TO_SCRIPT, ROUTING
    for lang in ("ml", "gu", "pa", "or", "si"):
        assert lang in LANG_TO_SCRIPT
        assert LANG_TO_SCRIPT[lang] in ROUTING
