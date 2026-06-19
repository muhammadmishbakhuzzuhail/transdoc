# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""XY-cut reading order (Area D, D1). Generalises the old equal-width band split: cuts at the
widest whitespace gutter, so it also handles UNEQUAL columns, nested structure and floats that the
fixed 3/2-col split couldn't. Plus the reading_order_match eval metric."""

from __future__ import annotations

from transdoc.eval.metrics import reading_order_match
from transdoc.extract.reading_order import reading_order
from transdoc.ir import BBox, Block, BlockType, Document


def _b(text, x0, y0, x1, y1, page=0):
    return Block(id=text, type=BlockType.PARAGRAPH, page=page, text=text,
                 bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def _ordered(doc):
    return [b.text for b in sorted(doc.blocks, key=lambda b: b.reading_order)]


def test_unequal_columns_wide_body_narrow_sidebar():
    # body 20-420, sidebar 460-580 — NOT equal width, so the old 2-col split would reject it and
    # interleave; XY-cut cuts at the 40pt gutter and reads body fully, then sidebar.
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [
        _b("S1", 460, 50, 580, 100), _b("BODY1", 20, 50, 420, 100),
        _b("BODY2", 20, 150, 420, 200), _b("S2", 460, 150, 580, 200),
    ]
    reading_order(d)
    assert _ordered(d) == ["BODY1", "BODY2", "S1", "S2"]


def test_nested_title_over_two_columns():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [
        _b("L1", 20, 80, 280, 140), _b("TITLE", 20, 20, 580, 45),
        _b("R1", 320, 80, 580, 140), _b("L2", 20, 160, 280, 220),
        _b("R2", 320, 160, 580, 220),
    ]
    reading_order(d)
    assert _ordered(d) == ["TITLE", "L1", "L2", "R1", "R2"]


def test_bottom_footnote_sorts_last():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [
        _b("FOOT", 20, 740, 580, 780),                # full-width footnote at the bottom
        _b("BODY", 20, 60, 580, 120),
    ]
    reading_order(d)
    assert _ordered(d) == ["BODY", "FOOT"]


def test_no_bbox_blocks_keep_append_order_last():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    a = _b("A", 20, 60, 580, 100)
    n1 = Block(id="N1", type=BlockType.PARAGRAPH, page=0, text="N1")   # no bbox
    n2 = Block(id="N2", type=BlockType.PARAGRAPH, page=0, text="N2")
    d.blocks = [n1, a, n2]
    reading_order(d)
    assert _ordered(d) == ["A", "N1", "N2"]


def test_metric_perfect_and_reversed():
    boxes = [(0, 0, 10, 10), (0, 20, 10, 30), (0, 40, 10, 50)]
    perfect = reading_order_match(boxes, boxes)
    assert perfect["kendall_tau"] == 1.0 and perfect["seq_accuracy"] == 1.0
    rev = reading_order_match(boxes, list(reversed(boxes)))
    assert rev["kendall_tau"] == -1.0 and rev["seq_accuracy"] == 0.0
    assert rev["coverage"] == 1.0


def test_metric_partial_coverage():
    refs = [(0, 0, 10, 10), (0, 20, 10, 30), (0, 40, 10, 50)]
    hyps = [(0, 0, 10, 10), (0, 40, 10, 50)]           # middle block missing
    m = reading_order_match(refs, hyps)
    assert m["matched"] == 2
    assert abs(m["coverage"] - 2 / 3) < 1e-9
    assert m["kendall_tau"] == 1.0                      # the two it found are in order
