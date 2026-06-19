# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Caption <-> figure/table association: a caption binds to its nearest media in the same
column band and is reordered to sit adjacent to it, even when a body paragraph slotted between."""

from __future__ import annotations

from transdoc.extract.base import associate_captions
from transdoc.ir import BBox, Block, BlockType, Document


def _blk(bid, t, y0, y1, x0=50, x1=300, ro=0):
    return Block(id=bid, type=t, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), reading_order=ro)


def test_figure_caption_below_binds_and_reorders():
    d = Document(source_path="x", mime="application/pdf")
    fig = _blk("fig", BlockType.FIGURE, 100, 300, ro=0)
    intruder = _blk("para", BlockType.PARAGRAPH, 305, 320, ro=1)   # sneaks between in bbox sort
    cap = _blk("cap", BlockType.CAPTION, 310, 330, ro=2)
    d.blocks = [fig, intruder, cap]
    associate_captions(d)
    assert cap.anchor_id == "fig"
    order = {b.id: b.reading_order for b in d.blocks}
    assert order["cap"] == order["fig"] + 1            # caption sits right after its figure


def test_table_caption_above_binds_before():
    d = Document(source_path="x", mime="application/pdf")
    cap = _blk("cap", BlockType.CAPTION, 90, 110, ro=0)
    tbl = _blk("tbl", BlockType.TABLE, 120, 300, ro=1)
    d.blocks = [cap, tbl]
    associate_captions(d)
    assert cap.anchor_id == "tbl"
    order = {b.id: b.reading_order for b in d.blocks}
    assert order["cap"] < order["tbl"]                 # caption above stays before its table


def test_no_horizontal_overlap_no_binding():
    d = Document(source_path="x", mime="application/pdf")
    fig = _blk("fig", BlockType.FIGURE, 100, 300, x0=50, x1=120)
    cap = _blk("cap", BlockType.CAPTION, 310, 330, x0=400, x1=520)  # other column
    d.blocks = [fig, cap]
    associate_captions(d)
    assert cap.anchor_id is None


def test_office_path_no_bbox_noop():
    d = Document(source_path="x", mime="docx")
    cap = Block(id="cap", type=BlockType.CAPTION, reading_order=0)
    d.blocks = [cap]
    associate_captions(d)                               # no bbox -> nothing happens, no crash
    assert cap.anchor_id is None
