# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""PP-StructureV3 OCR language selection. The structured extractor must OCR in the source
language, not PP-StructureV3's Chinese default (which turned non-Chinese scans to garbage)."""

from __future__ import annotations

from transdoc.layout.structure import paddle_lang


def test_explicit_langs_map_to_paddle_codes():
    assert paddle_lang("hi") == "hi"          # Devanagari — the regression case
    assert paddle_lang("zh") == "ch"
    assert paddle_lang("ja") == "japan"
    assert paddle_lang("ko") == "korean"
    assert paddle_lang("en") == "en"


def test_auto_defaults_to_en_not_chinese():
    assert paddle_lang("auto") == "en"        # saner Latin default than PP-StructureV3's 'ch'
    assert paddle_lang(None) == "en"


def test_case_insensitive():
    assert paddle_lang("HI") == "hi"
