# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""translate_document: glossary enforcement, token protection, dedupe — engine-agnostic."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document
from transdoc.translate.echo import EchoTranslator
from transdoc.translate.memory import PersistentTM


@pytest.fixture(autouse=True)
def _no_persistent_tm(monkeypatch):
    # keep the test hermetic: never read/write the real cross-run cache
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    PersistentTM._instance = None


def _doc(*texts: str) -> Document:
    d = Document(source_path="x.txt", mime="text/plain")
    d.blocks = [
        Block(id=f"b{i}", type=BlockType.PARAGRAPH, page=0, text=t,
              confidence=Confidence(source="digital"))
        for i, t in enumerate(texts)
    ]
    return d


def test_echo_translates_every_block():
    doc = _doc("Hello", "World")
    translate_document(doc, EchoTranslator(), Config(target_lang="id"))
    assert [b.output_text for b in doc.blocks] == ["[id] Hello", "[id] World"]
    assert doc.target_lang == "id"


def test_verbatim_tokens_survive_translation():
    doc = _doc("Contact a@b.com now")
    translate_document(doc, EchoTranslator(), Config(target_lang="id"))
    assert "a@b.com" in doc.blocks[0].output_text


def test_glossary_enforced_after_translation():
    doc = _doc("Welcome to ACME today")
    cfg = Config(target_lang="id", glossary={"ACME": "PUNCAK"})
    translate_document(doc, EchoTranslator(), cfg)
    assert "PUNCAK" in doc.blocks[0].output_text
    assert "ACME" not in doc.blocks[0].output_text


def test_identical_blocks_get_identical_output():
    doc = _doc("Same", "Same")
    translate_document(doc, EchoTranslator(), Config(target_lang="id"))
    assert doc.blocks[0].output_text == doc.blocks[1].output_text
