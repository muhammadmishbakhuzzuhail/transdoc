# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""IndicTrans2 engine: code mapping, direction selection, factory wiring. The model itself is
an optional heavy dep (lazy-loaded in translate_batch), so these cover the pure routing logic."""

from __future__ import annotations

from transdoc.config import Config, Engine
from transdoc.translate import get_translator
from transdoc.translate.indictrans import IndicTransTranslator, direction, to_code


def test_iso_to_indictrans_code():
    assert to_code("hi") == "hin_Deva"
    assert to_code("ta") == "tam_Taml"
    assert to_code("en") == "eng_Latn"


def test_unknown_lang_defaults_english():
    assert to_code("zz") == "eng_Latn"
    assert to_code(None) == "eng_Latn"
    assert to_code("auto") == "eng_Latn"


def test_direction_selection():
    assert direction("eng_Latn", "hin_Deva") == "en-indic"
    assert direction("hin_Deva", "eng_Latn") == "indic-en"
    assert direction("hin_Deva", "tam_Taml") == "indic-indic"


def test_factory_returns_indictrans_without_loading_model():
    # __init__ is lightweight (no torch import); the model loads only on translate_batch.
    tr = get_translator(Config(target_lang="hi", engine=Engine.INDICTRANS))
    assert isinstance(tr, IndicTransTranslator) and tr.name == "indictrans"


def test_empty_batch_short_circuits():
    tr = IndicTransTranslator()
    assert tr.translate_batch([], Config(target_lang="hi")) == []


def test_to_code_normalises_bcp47_and_case():
    # regioned / uppercase codes must resolve, not silently fall through to the English default
    assert to_code("hi") == to_code("hi-IN") == to_code("HI") == "hin_Deva"
    assert to_code("ta-IN") == "tam_Taml"
