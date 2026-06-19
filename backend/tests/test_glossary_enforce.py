# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Glossary enforcement through translate_document: a supplied source->target term overrides
the engine output and is applied consistently (keys are protected verbatim, then mapped)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document
from transdoc.translate.echo import EchoTranslator


def test_glossary_terms_enforced():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="b", type=BlockType.PARAGRAPH, page=0,
                        text="The Transformer uses attention.",
                        confidence=Confidence(source="digital"))]
    cfg = Config(target_lang="id", glossary={"Transformer": "Transformator",
                                             "attention": "atensi"})
    translate_document(doc, EchoTranslator(), cfg)
    out = doc.blocks[0].translated
    assert "Transformator" in out and "atensi" in out
    assert "Transformer" not in out


def test_auto_glossary_terms_mining():
    from transdoc.translate.base import _auto_glossary_terms
    texts = ["Transdoc is great.", "I use Transdoc daily.",            # single proper -> mine
             "The API works.", "Call the API now.",                     # acronym -> mine
             "Hugging Face model.", "Use Hugging Face.",                 # phrase -> not split/mined
             "The cat sat.", "Document the document please."]           # common/inflected -> skip
    mined = _auto_glossary_terms(texts)
    assert "Transdoc" in mined and "API" in mined
    assert "Hugging" not in mined and "Face" not in mined and "Document" not in mined
    assert _auto_glossary_terms(["The quick brown fox.", "A lazy dog."]) == []


def test_auto_glossary_skips_capitalized_words_for_noun_capitalizing_langs():
    """German capitalizes EVERY common noun, so an initial capital is not a proper-noun signal.
    The single-Capitalized-word pass would mine ordinary nouns ("Mark", "Posten") and pin a wrong
    standalone rendering; it must be skipped for German/Luxembourgish. Acronyms still mine (the
    all-caps shape is language-independent)."""
    from transdoc.translate.base import _auto_glossary_terms
    texts = ["1 Mark 50 Pfennig", "4 Mark 80 Pfennig",        # currency nouns -> must NOT mine
             "Front bei Arras", "An der Front",                # ordinary noun -> must NOT mine
             "Bericht der NATO", "NATO meldet"]                # acronym -> still mines
    de = _auto_glossary_terms(texts, src="de")
    assert de == ["NATO"]                                      # only the acronym
    # English (proper-noun-signalling): the same shape still mines capitalized words
    en = _auto_glossary_terms(["Mark arrived", "Mark left", "NATO meldet", "NATO again"], src="en")
    assert "Mark" in en and "NATO" in en


class _DriftEngine:
    """Real-ish engine: keeps the proper noun verbatim in prose, and renders it canonically when
    asked in isolation — so only the auto-glossary can enforce one rendering everywhere."""
    cacheable = True

    def translate_batch(self, texts, cfg, src=None):
        return ["Transdok" if t == "Transdoc" else t for t in texts]


def test_auto_glossary_enforces_proper_noun_consistency():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [
        Block(id="a", type=BlockType.PARAGRAPH, page=0, text="Transdoc appears here.",
              confidence=Confidence(source="digital")),
        Block(id="b", type=BlockType.PARAGRAPH, page=0, text="I really like Transdoc.",
              confidence=Confidence(source="digital")),
    ]
    translate_document(doc, _DriftEngine(), Config(target_lang="id"))
    for b in doc.blocks:
        assert "Transdok" in b.translated and "Transdoc" not in b.translated


def test_auto_glossary_off_by_flag():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="a", type=BlockType.PARAGRAPH, page=0, text="Transdoc here.",
                        confidence=Confidence(source="digital"))]
    translate_document(doc, _DriftEngine(), Config(target_lang="id", auto_glossary=False))
    assert "Transdoc" in doc.blocks[0].translated   # not pinned when disabled
