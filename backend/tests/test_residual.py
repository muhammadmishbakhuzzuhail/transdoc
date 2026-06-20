# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Residual foreign-script cleanup: non-Latin runs the engine left in a Latin-target output get
re-translated; runs of different scripts are handled separately; non-Latin targets are skipped."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document
from transdoc.translate.residual import retranslate_foreign_runs, _FOREIGN


class _Stub:
    cacheable = True
    _MAP = {"中文文本。": "teks Cina", "العربية": "Arab", "世界": "dunia"}

    def translate_batch(self, texts, cfg, src=None):
        return [self._MAP.get(t.strip(), t) for t in texts]


def _doc(translated):
    d = Document(source_path="x", mime="docx")
    b = Block(id="1", type=BlockType.PARAGRAPH, text="x")
    b.translated = translated
    d.blocks = [b]
    return d, b


def test_splits_runs_by_script():
    # different scripts separated by a space must be separate runs (so each is detected on its own)
    assert _FOREIGN.findall("a 中文文本。 العربية b") == ["中文文本。", "العربية"]


def test_retranslates_leftover_foreign_runs():
    d, b = _doc("Bahasa inggris. 中文文本。 العربية. Terima kasih")
    n = retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="id"))
    assert n == 1
    assert "teks Cina" in b.translated and "Arab" in b.translated
    assert "中文" not in b.translated and "العربية" not in b.translated


def test_skips_non_latin_target():
    # target is Chinese -> foreign script is expected, don't touch it
    d, b = _doc("世界 hello")
    assert retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="zh")) == 0
    assert b.translated == "世界 hello"


def test_noop_when_no_foreign():
    d, b = _doc("Teks Indonesia biasa saja.")
    assert retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="id")) == 0


def test_detects_late_indic_scripts():
    # Kannada/Gujarati/Gurmukhi/Oriya/Sinhala were missing from the foreign-run ranges -> inline
    # runs in these scripts went undetected and untranslated in a Latin-target output.
    for s in ("ಕನ್ನಡ", "ગુજરાતી", "ਪੰਜਾਬੀ", "ଓଡ଼ିଆ", "සිංහල"):
        assert _FOREIGN.search(s), s


def test_skips_non_latin_target_derived():
    # derived from LANG_TO_SCRIPT: sa (Sanskrit/Devanagari) and gu/or/si must be skipped so their
    # own correct script output isn't re-translated as a foreign leftover.
    from transdoc.translate.residual import _non_latin_targets
    nl = _non_latin_targets()
    assert {"sa", "gu", "pa", "or", "si", "kn", "ps", "dv"} <= nl
    assert "id" not in nl and "en" not in nl
