# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""OCR engine routing (ScriptRoutedOCR._chain): an explicit non-Latin source language must get the
script-optimised paddle-first chain, not the tesseract-first default — the bug that turned
`--source hi` on a Devanagari scan into garbage."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ocr import router
from transdoc.ocr.router import DEFAULT_CHAIN, ScriptRoutedOCR


def _chain(source_lang):
    return ScriptRoutedOCR()._chain(b"", Config(source_lang=source_lang, target_lang="id"))


def test_explicit_devanagari_routes_paddle_first():
    assert _chain("hi")[0] == "paddle"          # was tesseract-first -> garbage


def test_explicit_cjk_routes_paddle_first():
    assert _chain("zh")[0] == "paddle"
    assert _chain("ja")[0] == "paddle"
    assert _chain("ko")[0] == "paddle"


def test_explicit_latin_keeps_tesseract_first():
    assert _chain("en") == DEFAULT_CHAIN         # tesseract-first is right for Latin
    assert _chain("fr") == DEFAULT_CHAIN
    assert _chain("de")[0] == "tesseract"


def test_case_insensitive():
    assert _chain("HI")[0] == "paddle"


def test_auto_uses_script_detection(monkeypatch):
    monkeypatch.setattr(router, "detect_script", lambda img: "Devanagari")
    assert _chain("auto")[0] == "paddle"
    monkeypatch.setattr(router, "detect_script", lambda img: "Latin")
    assert _chain("auto")[0] == "tesseract"


def test_auto_unknown_script_falls_back_to_default(monkeypatch):
    monkeypatch.setattr(router, "detect_script", lambda img: None)
    assert _chain("auto") == DEFAULT_CHAIN
