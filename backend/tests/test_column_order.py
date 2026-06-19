# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Multi-column reading order: left column read fully before right; single column unaffected;
full-width blocks break bands (research: naive y-sort interleaves columns)."""

from __future__ import annotations

from transdoc.extract.base import column_reading_order
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _b(text, x0, y0, x1, y1, page=0):
    return Block(id=text, type=BlockType.PARAGRAPH, page=page, text=text,
                 bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=Confidence())


def _ordered(doc):
    return [b.text for b in sorted(doc.blocks, key=lambda b: b.reading_order)]


def test_two_column_reads_left_then_right():
    # page width 600, gutter at 300. Left col L1(top) L2(bottom); right col R1 R2.
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [
        _b("R1", 320, 50, 580, 100), _b("L1", 20, 50, 280, 100),
        _b("L2", 20, 150, 280, 200), _b("R2", 320, 150, 580, 200),
    ]
    column_reading_order(d)
    assert _ordered(d) == ["L1", "L2", "R1", "R2"]   # not interleaved L1,R1,L2,R2


def test_full_width_title_breaks_columns():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [
        _b("TITLE", 20, 20, 580, 45),                 # full width -> band break
        _b("L1", 20, 60, 280, 120), _b("R1", 320, 60, 580, 120),
        _b("FOOTER", 20, 700, 580, 730),              # full width
    ]
    column_reading_order(d)
    assert _ordered(d) == ["TITLE", "L1", "R1", "FOOTER"]


def test_three_column_reads_column_by_column():
    # page width 900, three 300pt columns. Each column top-then-bottom, columns left-to-right.
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (900.0, 800.0)
    d.blocks = [
        _b("C1", 620, 50, 880, 100), _b("A1", 20, 50, 280, 100), _b("B1", 320, 50, 580, 100),
        _b("B2", 320, 150, 580, 200), _b("A2", 20, 150, 280, 200), _b("C2", 620, 150, 880, 200),
    ]
    column_reading_order(d)
    assert _ordered(d) == ["A1", "A2", "B1", "B2", "C1", "C2"]


def test_single_column_is_top_to_bottom():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = [_b("B", 40, 300, 560, 340), _b("A", 40, 100, 560, 140)]
    column_reading_order(d)
    assert _ordered(d) == ["A", "B"]
