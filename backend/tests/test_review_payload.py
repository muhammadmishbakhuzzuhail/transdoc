# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""build_review payload (PR-6): segments carry bbox (PDF points) + page sizes so the review UI can
map a clicked segment onto the rasterised page preview. Ordered by reading order."""

from __future__ import annotations

from transdoc.api.review import build_review
from transdoc.ir import BBox, Block, BlockType, Document, Style


def _doc():
    d = Document(source_path="x.pdf", mime="application/pdf", page_count=1,
                 source_lang="en", target_lang="id")
    d.page_sizes = {0: (595.0, 842.0)}
    b0 = Block(id="b0", type=BlockType.PARAGRAPH, page=0, reading_order=1, text="World",
               bbox=BBox(x0=10, y0=60, x1=200, y1=80), style=Style(size=11))
    b0.translated = "Dunia"
    b1 = Block(id="b1", type=BlockType.TITLE, page=0, reading_order=0, text="Hello",
               bbox=BBox(x0=10, y0=20, x1=200, y1=40), style=Style(size=20))
    b1.translated = "Halo"
    d.blocks = [b0, b1]
    return d


def test_payload_has_bbox_and_page_sizes_in_reading_order():
    p = build_review(_doc())
    assert p["src_lang"] == "en" and p["tgt_lang"] == "id"
    assert p["page_sizes"] == {"0": [595.0, 842.0]}
    # ordered_blocks sorts by (page, reading_order) -> title (ro=0) before body (ro=1)
    assert [s["block_id"] for s in p["segments"]] == ["b1", "b0"]
    assert p["segments"][0]["bbox"] == [10, 20, 200, 40]
    assert p["segments"][0]["translation"] == "Halo"


def test_untranslated_blocks_excluded():
    d = _doc()
    extra = Block(id="b2", type=BlockType.PARAGRAPH, page=0, reading_order=2, text="untranslated")
    d.blocks.append(extra)               # no .translated -> dropped
    p = build_review(d)
    assert "b2" not in [s["block_id"] for s in p["segments"]]
