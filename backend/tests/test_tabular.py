# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Numeric table rows the PDF parser merged into one block are preserved verbatim, so the
grid survives instead of reflowing into running text when translated."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.extract.pdf import _looks_tabular
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document
from transdoc.translate.echo import EchoTranslator


def test_detects_numeric_table_rows():
    assert _looks_tabular("BERTBASE 84.4 88.4 86.7 92.7 88.5 No NSP 83.9 84.9 86.5 92.6 87.9")
    assert _looks_tabular("base 6 512 2048 8 64 64 0.1 0.1 100K 4.92 25.8 65")


def test_prose_not_tabular():
    assert not _looks_tabular("In this work we employ h = 8 parallel attention layers today.")
    assert not _looks_tabular("The model reached 92.7 percent accuracy on the test set.")
    assert not _looks_tabular("short line")


def test_dotted_leaders_not_tabular():
    # IRS form line-items: dotted leaders (". . . . .") must NOT count as numeric tokens,
    # else the English label row gets frozen verbatim and never translated.
    assert not _looks_tabular(
        "1 a Total amount from Form(s) W-2, box 1 (see instructions) . . . . . . 1a")
    assert not _looks_tabular(
        "2a Tax-exempt interest . . . 2a b Taxable interest . . . . . . . 2b")


def test_merged_table_block_left_verbatim():
    doc = Document(source_path="x.pdf", mime="application/pdf")
    # a TABLE-typed block with no .table = merged numeric rows -> must not be translated
    doc.blocks = [
        Block(id="t", type=BlockType.TABLE, page=0,
              text="BERTBASE 84.4 88.4 No NSP 83.9 84.9 LTR 82.1 84.3",
              confidence=Confidence(source="digital")),
        Block(id="p", type=BlockType.PARAGRAPH, page=0, text="Hello",
              confidence=Confidence(source="digital")),
    ]
    translate_document(doc, EchoTranslator(), Config(target_lang="id"))
    assert doc.blocks[0].translated is None              # table block untouched
    assert doc.blocks[1].translated == "[id] Hello"      # prose translated
