# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""FLOW reading order: rotated/vertical sidebar blocks are moved to the end of their page so
they don't interrupt the reflowed text; normal blocks keep their relative order."""

from __future__ import annotations

from transdoc.extract.base import reorder_vertical_last
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _b(bid, page, order, bbox):
    return Block(id=bid, type=BlockType.PARAGRAPH, page=page, text=bid,
                 reading_order=order, bbox=BBox(x0=bbox[0], y0=bbox[1], x1=bbox[2], y1=bbox[3]),
                 confidence=Confidence(source="digital"))


def test_vertical_moved_to_page_end():
    doc = Document(source_path="x.pdf", mime="application/pdf", page_count=2)
    doc.blocks = [
        _b("p0-title", 0, 0, (50, 10, 500, 30)),
        _b("p0-vert", 0, 1, (10, 20, 30, 700)),       # tall+narrow -> vertical
        _b("p0-body", 0, 2, (50, 40, 500, 200)),
        _b("p1-body", 1, 0, (50, 10, 500, 200)),
    ]
    reorder_vertical_last(doc)
    order = [b.id for b in doc.ordered_blocks()]
    # vertical pushed after the page-0 normal blocks, before page 1; normal order preserved
    assert order == ["p0-title", "p0-body", "p0-vert", "p1-body"]


def test_no_vertical_keeps_order():
    doc = Document(source_path="x.pdf", mime="application/pdf", page_count=1)
    doc.blocks = [
        _b("a", 0, 0, (50, 10, 500, 30)),
        _b("b", 0, 1, (50, 40, 500, 200)),
    ]
    reorder_vertical_last(doc)
    assert [b.id for b in doc.ordered_blocks()] == ["a", "b"]
