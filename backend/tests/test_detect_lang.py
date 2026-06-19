# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Language detection: lingua backend (opt-in) with langdetect fallback."""

from __future__ import annotations

import pytest

from transdoc import diagnose
from transdoc.diagnose import _lingua_detect, detect_lang


@pytest.fixture(autouse=True)
def _reset_lingua_cache():
    diagnose._LINGUA = {"tried": False, "detector": None}
    yield
    diagnose._LINGUA = {"tried": False, "detector": None}


def test_detect_lang_english_either_backend():
    # works regardless of which backend is installed
    assert detect_lang("This is a clearly English sentence about cats and dogs.") == "en"


def test_disable_lingua_env_forces_fallback(monkeypatch):
    monkeypatch.setenv("TRANSDOC_DISABLE_LINGUA", "1")
    assert _lingua_detect("This is an English sentence.") is None
    # detect_lang still works via langdetect
    assert detect_lang("This is a clearly English sentence about cats and dogs.") == "en"


def test_lingua_detects_iso_code():
    pytest.importorskip("lingua")
    # lingua fixes langdetect's Chinese-as-Korean full-text miss
    assert _lingua_detect("This is a longer English passage with several words.") == "en"
    assert _lingua_detect("Это предложение написано на русском языке полностью.") == "ru"
