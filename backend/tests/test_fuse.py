# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Cross-source reconcile: drop text inside a non-text region (anti-overwrite) + dedup text."""

from __future__ import annotations

from transdoc.extract.fuse import reconcile
from transdoc.ir import BBox, Block, BlockType, Confidence


def _b(t, x0, y0, x1, y1, text=""):
    return Block(id=text or t.value, type=t, text=text,
                 bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), confidence=Confidence())


def test_drops_text_inside_figure():
    fig = _b(BlockType.FIGURE, 0, 0, 200, 200)
    caption_inside = _b(BlockType.PARAGRAPH, 20, 20, 180, 60, "label baked into the diagram")
    real_text = _b(BlockType.PARAGRAPH, 0, 300, 400, 340, "a normal paragraph below the figure")
    out = reconcile([fig, caption_inside, real_text])
    texts = [b.text for b in out if b.type == BlockType.PARAGRAPH]
    assert "a normal paragraph below the figure" in texts
    assert "label baked into the diagram" not in texts   # inside the figure -> dropped
    assert any(b.type == BlockType.FIGURE for b in out)   # figure kept


def test_dedups_overlapping_text_keeps_longer():
    short = _b(BlockType.PARAGRAPH, 40, 300, 500, 330, "the full sentence about scaled dot")
    full = _b(BlockType.PARAGRAPH, 41, 301, 501, 331,
              "the full sentence about scaled dot product attention indeed")
    out = reconcile([short, full])
    paras = [b for b in out if b.type == BlockType.PARAGRAPH]
    assert len(paras) == 1 and "attention indeed" in paras[0].text


def test_keeps_formula_and_table_regions():
    tbl = _b(BlockType.TABLE, 0, 0, 300, 100)
    formula = _b(BlockType.FORMULA, 0, 120, 200, 150)
    out = reconcile([tbl, formula])
    assert len(out) == 2   # non-text regions never dropped
