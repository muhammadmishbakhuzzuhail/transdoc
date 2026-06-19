# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Text normalization: de-hyphenation across line breaks, ligature folding, NFC, zero-width."""

from __future__ import annotations

from transdoc.extract.textnorm import clean, normalize_doc
from transdoc.ir import BBox, Block, BlockType, Cell, Confidence, Document, Table


def test_dehyphenates_line_break():
    assert clean("inter-\nnational") == "international"
    assert clean("base-\nline shift") == "baseline shift"


def test_dehyphenates_space_joined():
    # blocks are space-joined before normalize (OCR/structured/PDF) — the newline is already gone,
    # so de-hyphenation must also handle "inter- national" with a space.
    assert clean("inter- national law") == "international law"
    assert clean("co- operate now") == "cooperate now"


def test_keeps_real_hyphen_and_inline_text():
    assert clean("well-known method") == "well-known method"   # no newline -> untouched
    assert clean("a-\n1") == "a-\n1"                            # digit side -> not a word break
    assert clean("well- Known brand") == "well- Known brand"   # uppercase after -> keep (compound)
    assert clean("range 10 - 20 ok") == "range 10 - 20 ok"     # digits -> keep range
    assert clean("state-of-the-art") == "state-of-the-art"     # no space -> keep compound


def test_folds_ligatures():
    assert clean("eﬃcient ﬁle ﬂow") == "efficient file flow"


def test_strips_soft_hyphen_and_zero_width():
    assert clean("soft­hyphen") == "softhyphen"
    assert clean("zero​width") == "zerowidth"


def test_nfc_normalizes():
    # combining acute (e + U+0301) -> single é (U+00E9)
    assert clean("é") == "é"


def test_normalize_doc_cleans_blocks_and_cells():
    d = Document(source_path="x", mime="application/pdf")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    d.blocks = [
        Block(id="1", type=BlockType.PARAGRAPH, text="trans-\nlation", bbox=bb,
              confidence=Confidence()),
        Block(id="2", type=BlockType.TABLE, bbox=bb, confidence=Confidence(),
              table=Table(rows=[[Cell(text="ﬁeld"), Cell(text="va-\nlue")]])),
    ]
    normalize_doc(d)
    assert d.blocks[0].text == "translation"
    assert d.blocks[1].table.rows[0][0].text == "field"
    assert d.blocks[1].table.rows[0][1].text == "value"
