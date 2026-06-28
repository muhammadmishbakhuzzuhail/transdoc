# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""NLLB FLORES-200 code mapping: an unmapped target must NOT silently fall back to English
(the silent-passthrough bug the head-to-head benchmark caught on Bengali). Pure logic — no model."""

from __future__ import annotations

import pytest

from transdoc.translate.nllb import NLLB_CODE, NLLBTranslator


def _coder():
    # bypass __init__ (which loads the ~2.5 GB model) — _code is pure
    return object.__new__(NLLBTranslator)


def test_bengali_and_other_targets_are_mapped_not_english():
    c = _coder()
    assert c._code("bn", "eng_Latn", required=True) == "ben_Beng"     # the regression
    assert c._code("ta", "eng_Latn", required=True) == "tam_Taml"
    assert c._code("uk", "eng_Latn", required=True) == "ukr_Cyrl"
    assert c._code("tr", "eng_Latn", required=True) == "tur_Latn"


def test_unmapped_target_raises_instead_of_silent_passthrough():
    c = _coder()
    with pytest.raises(ValueError, match="unsupported target"):
        c._code("xx", "eng_Latn", required=True)


def test_region_code_falls_back_to_base_language():
    c = _coder()
    assert c._code("zh-CN", "eng_Latn", required=True) == "zho_Hans"


def test_auto_or_empty_uses_default():
    c = _coder()
    assert c._code("auto", "eng_Latn") == "eng_Latn"
    assert c._code(None, "eng_Latn") == "eng_Latn"


def test_ui_shortlist_languages_all_mapped():
    # every language the frontend picker offers must have a FLORES code (no English passthrough)
    ui = ["id", "en", "ar", "zh", "ja", "ko", "de", "fr", "es", "pt", "it", "nl", "ru", "uk",
          "pl", "cs", "ro", "el", "tr", "sv", "da", "fi", "no", "nb", "bg", "hr", "sr", "sk",
          "hi", "bn", "ta", "te", "ur", "fa", "he", "th", "vi", "ms", "fil", "sw", "af"]
    missing = [lg for lg in ui if lg not in NLLB_CODE]
    assert not missing, f"NLLB_CODE missing UI languages: {missing}"
