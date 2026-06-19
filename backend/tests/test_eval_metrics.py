# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Eval metrics: chrF (translation), CER/WER (OCR/text), structure counts, baseline diff."""

from __future__ import annotations

from transdoc.eval.metrics import cer, chrf, edit_distance, structure_metrics, wer
from transdoc.ir import BBox, Block, BlockType, Cell, Confidence, Document, Table


def test_chrf_identical_and_unrelated():
    assert chrf("the quick brown fox", "the quick brown fox") == 100.0
    assert chrf("the quick brown fox", "zzz xkcd qwerty") < 20
    assert chrf("", "") == 0.0


def test_edit_distance():
    assert edit_distance(list("kitten"), list("sitting")) == 3
    assert edit_distance([], [1, 2]) == 2
    assert edit_distance([1, 2, 3], [1, 2, 3]) == 0


def test_cer_wer():
    assert cer("hello", "hello") == 0.0
    assert cer("hello", "hallo") == 0.2          # 1 of 5 chars wrong
    assert wer("the cat sat", "the cat sat") == 0.0
    assert abs(wer("the cat sat", "the dog sat") - 1 / 3) < 1e-9
    # empty reference: perfect iff hyp also empty, else fully wrong
    assert cer("", "") == 0.0 and cer("", "x") == 1.0
    assert wer("", "") == 0.0 and wer("", "x") == 1.0


def _doc():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    tbl = Table(rows=[[Cell(text="a"), Cell(text="b")], [Cell(text="c"), Cell(text="d")]])
    d.blocks = [
        Block(id="1", type=BlockType.PARAGRAPH, reading_order=0, bbox=bb, text="hello",
              confidence=Confidence()),
        Block(id="2", type=BlockType.FORMULA, reading_order=1, bbox=bb, text=r"\frac{a}{b}",
              confidence=Confidence()),
        Block(id="3", type=BlockType.TABLE, reading_order=2, bbox=bb, table=tbl,
              confidence=Confidence()),
        Block(id="4", type=BlockType.FIGURE, reading_order=3, bbox=bb, crop_region=True,
              confidence=Confidence()),
    ]
    return d


def test_structure_metrics():
    m = structure_metrics(_doc())
    assert m["blocks"] == 4
    assert m["formulas"] == 1
    assert m["tables"] == 1
    assert m["table_cells"] == 4
    assert m["figures"] == 1
    assert m["reading_order_monotonic"] is True
    # formula/figure are non-translatable; only the paragraph is
    assert m["translatable"] == 1


def test_structure_metrics_detects_nonmonotonic_order():
    d = _doc()
    d.blocks[0].reading_order = 99    # out of order
    assert structure_metrics(d)["reading_order_monotonic"] is False
