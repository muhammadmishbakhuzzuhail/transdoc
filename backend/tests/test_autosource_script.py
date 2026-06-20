# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Auto source on a scan/image resolves the OCR language from the page script (OSD), so a
non-Latin scan picks the right model instead of a Latin/Chinese default that yields garbage."""

from __future__ import annotations

import types

from transdoc.ingest.detect import Kind
from transdoc import pipeline


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
