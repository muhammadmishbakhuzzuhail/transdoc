"""Tesseract auto-script detection: a non-Latin scan with source=auto must pick the matching
lang pack (via OSD) instead of defaulting to 'eng' and returning Latin gibberish."""

from __future__ import annotations

import pytest

from transdoc.config import Config

pytest.importorskip("pytesseract")
import pytesseract  # noqa: E402

from transdoc.ocr.tesseract import _SCRIPT_LANG, TesseractOCR  # noqa: E402

_AVAIL = set(pytesseract.get_languages(config=""))


def test_script_map_has_major_scripts():
    for script, lang in [("Devanagari", "hin"), ("Han", "chi_sim"), ("Arabic", "ara"),
                         ("Cyrillic", "rus"), ("Hangul", "kor"), ("Thai", "tha")]:
        assert _SCRIPT_LANG[script] == lang


def test_detected_lang_used_when_source_auto():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="auto")
    langs = tr._langs(cfg, detected="hin" if "hin" in _AVAIL else None)
    if "hin" in _AVAIL:
        assert "hin" in langs.split("+")
    assert "eng" in langs.split("+")          # eng always kept as a backstop


def test_explicit_source_overrides_detection():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="ru")
    langs = tr._langs(cfg, detected="hin")    # explicit source wins; detected ignored
    assert "hin" not in langs.split("+")


def test_no_detection_falls_back_to_eng():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="auto")
    assert tr._langs(cfg, detected=None) == "eng"
