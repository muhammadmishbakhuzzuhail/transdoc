# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""AUTO fidelity routes a same-script MULTI-COLUMN PDF to FLOW: the positioned reconstruct
overprints columns when the translation expands (verified on arXiv en->id), so two side-by-side
text columns must reflow. Single-column docs stay on reconstruct."""

from __future__ import annotations

from transdoc.ir import BBox, Block, BlockType, Document
from transdoc.pipeline import _is_multicolumn


def _b(bid, x0, y0, x1, y1):
    return Block(id=bid, type=BlockType.PARAGRAPH, page=0, text="some body text here",
                 bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1))


def _doc(blocks):
    d = Document(source_path="x.pdf", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (600.0, 800.0)
    d.blocks = blocks
    return d


def test_two_side_by_side_columns_is_multicolumn():
    # left column x 40-280, right column x 320-560, both spanning the same vertical band
    left = [_b(f"l{i}", 40, 100 + i * 120, 280, 200 + i * 120) for i in range(3)]
    right = [_b(f"r{i}", 320, 100 + i * 120, 560, 200 + i * 120) for i in range(3)]
    assert _is_multicolumn(_doc(left + right)) is True


def test_single_column_is_not_multicolumn():
    # one full-width column stacked vertically
    blocks = [_b(f"p{i}", 60, 100 + i * 90, 540, 170 + i * 90) for i in range(6)]
    assert _is_multicolumn(_doc(blocks)) is False


def test_too_few_blocks_is_not_multicolumn():
    assert _is_multicolumn(_doc([_b("a", 40, 100, 280, 200), _b("b", 320, 100, 560, 200)])) is False


def test_sequential_indented_blocks_not_multicolumn():
    # blocks at different x but NOT vertically overlapping (sequential, e.g. an indented quote) must
    # not be mistaken for columns
    blocks = [_b("p0", 60, 100, 540, 160), _b("p1", 120, 200, 480, 260),
              _b("p2", 60, 300, 540, 360), _b("p3", 120, 400, 480, 460)]
    assert _is_multicolumn(_doc(blocks)) is False
