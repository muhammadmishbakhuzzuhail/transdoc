# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""reconcile: drop small labels inside a figure, but KEEP (and flag) a large text block a
mis-sized region happens to cover — never silently lose real prose."""

from __future__ import annotations

from transdoc.extract.fuse import reconcile
from transdoc.ir import BBox, Block, BlockType, Confidence


def _b(bid, t, text, x0, y0, x1, y1):
    return Block(id=bid, type=t, text=text, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                 confidence=Confidence())


def test_small_label_inside_figure_dropped():
    fig = _b("f", BlockType.FIGURE, "", 0, 0, 400, 400)
    label = _b("l", BlockType.CAPTION, "Fig 1", 10, 10, 80, 25)   # small label
    out = reconcile([fig, label])
    assert [b.id for b in out] == ["f"]                          # label dropped


def test_large_text_in_oversized_region_kept_and_flagged():
    fig = _b("f", BlockType.FIGURE, "", 0, 0, 400, 400)           # over-sized region
    prose = _b("p", BlockType.PARAGRAPH,
               "This is a long paragraph of real body text " * 6, 10, 40, 390, 360)
    out = reconcile([fig, prose])
    kept = {b.id for b in out}
    assert "p" in kept                                           # real prose NOT dropped
    p = next(b for b in out if b.id == "p")
    assert "region_overlap" in p.flags                          # flagged for review


def test_uncovered_text_untouched():
    para = _b("p", BlockType.PARAGRAPH, "normal text here that is long enough", 10, 10, 300, 40)
    out = reconcile([para])
    assert [b.id for b in out] == ["p"] and "region_overlap" not in out[0].flags
