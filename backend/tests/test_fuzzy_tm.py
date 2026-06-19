# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Fuzzy TM (PR-4): lexical scoring, the auto-apply safety gate (near-identical + same protected
tokens), the 75–95% suggestion tier, and end-to-end reuse through translate_document. The embedding
backend is optional, so these tests exercise the lexical path (no sentence-transformers needed)."""

from __future__ import annotations

import pytest

from transdoc.config import Config, Engine
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.store.tm import lexical_ratio


@pytest.fixture
def tm(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "fz.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    store = TMStore.get()
    yield store
    TMStore._instance = None


def test_lexical_ratio_basic():
    assert lexical_ratio("Pay 100 dollars now", "Pay 100 dollars now") == 1.0
    assert lexical_ratio("totally different", "x y z") < 0.4


def test_fuzzy_search_finds_similar_source(tm):
    tm.put_many({"The meeting starts at noon": "Rapat mulai siang"}, "id", src_lang="en")
    cands = tm.fuzzy_search("The meeting starts at noon.", "id", src_lang="en")
    assert cands and cands[0][1] == "Rapat mulai siang"
    assert cands[0][2] >= 0.9                         # near-identical (just a trailing period)


def test_fuzzy_search_scope_and_token_prefilter(tm):
    tm.put_many({"completely unrelated text": "teks"}, "id", src_lang="en")
    assert tm.fuzzy_search("nothing shares tokens here", "id", src_lang="en") == []


def _doc(text):
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.source_lang = "en"
    b = Block(id="b", type=BlockType.PARAGRAPH, page=0, text=text,
              confidence=Confidence(source="digital"))
    doc.blocks = [b]
    return doc


def test_auto_apply_reuses_when_tokens_match(tm):
    from transdoc.translate import get_translator, translate_document
    tm.put_many({"The annual report is ready": "Laporan tahunan siap"}, "id", src_lang="en")
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO)
    doc = _doc("The annual report is ready!")          # near-identical, no protected tokens differ
    translate_document(doc, get_translator(cfg), cfg)
    assert doc.blocks[0].translated == "Laporan tahunan siap"   # reused, NOT echo
    assert "fuzzy_auto" in doc.blocks[0].flags


def test_no_auto_apply_when_number_differs(tm):
    """Same wording, different number -> protected tokens differ -> must NOT reuse the past value."""
    from transdoc.translate import get_translator, translate_document
    tm.put_many({"Pay 100 dollars now": "Bayar 100 dolar sekarang"}, "id", src_lang="en")
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO)
    doc = _doc("Pay 200 dollars now")
    translate_document(doc, get_translator(cfg), cfg)
    assert doc.blocks[0].translated != "Bayar 100 dolar sekarang"   # not blindly reused
    assert "fuzzy_auto" not in doc.blocks[0].flags


def test_suggestion_tier_flags_but_engine_runs(tm):
    from transdoc.translate import get_translator, translate_document
    tm.put_many({"The quick brown fox jumps over the lazy dog":
                 "Rubah coklat cepat melompati anjing malas"}, "id", src_lang="en")
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO)
    # share many tokens but differ enough to land in the 75–95% band (not auto)
    doc = _doc("The quick brown fox leaps over a sleepy dog")
    translate_document(doc, get_translator(cfg), cfg)
    b = doc.blocks[0]
    if "fuzzy_auto" not in b.flags:                   # expected: suggestion, engine translated
        assert "fuzzy_suggest" in b.flags
        assert doc.fuzzy_suggestions and doc.fuzzy_suggestions[0][0] == b.text


def test_fuzzy_disabled(tm):
    from transdoc.translate import get_translator, translate_document
    tm.put_many({"Hello there friend": "Halo teman"}, "id", src_lang="en")
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO, fuzzy_tm=False)
    doc = _doc("Hello there friend!")
    translate_document(doc, get_translator(cfg), cfg)
    assert "fuzzy_auto" not in doc.blocks[0].flags    # disabled -> engine echo
