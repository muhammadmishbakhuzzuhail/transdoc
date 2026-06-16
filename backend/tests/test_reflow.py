"""Area C — text-expansion reflow in the positioned PDF reconstruction.

When a translation expands past its source box, the renderer tiers its response: compress leading,
grow into whitespace, cascade the following same-column blocks down, then spill onto a fresh page
(page count may grow — the DeepL reflow). Content that does NOT expand renders verbatim at its
original position, so an unexpanded doc keeps its exact 1:1 source-page layout.

The cascade/spill maths live in the pure ``_reflow`` / ``_columns`` helpers, tested directly here;
one end-to-end render confirms the wiring + page-count growth.
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style  # noqa: E402
from transdoc.regenerate.pdf_out import (  # noqa: E402
    _columns,
    _reflow,
    render_reconstruct,
)


def _item(bid, x0, y0, x1, y1, need, ro=0):
    """A reflow item: a block at a bbox needing ``need`` pt of height."""
    b = Block(id=bid, type=BlockType.PARAGRAPH, page=0, text="x", reading_order=ro,
              bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), style=Style(size=11),
              confidence=Confidence(source="digital"))
    return {"block": b, "rect": fitz.Rect(x0, y0, x1, y1), "h": need, "kind": "text"}


def test_no_expansion_renders_verbatim():
    # two stacked blocks that need exactly their box height -> keep original y, no overflow
    items = [_item("a", 20, 20, 380, 50, need=30, ro=0),
             _item("b", 20, 60, 380, 90, need=30, ro=1)]
    placements, overflow = _reflow(items, page_h=300, anchored=True)
    assert overflow == []
    assert placements["a"] == (20, 50)        # untouched original rect
    assert placements["b"] == (60, 90)


def test_cascade_pushes_following_block():
    # 'a' expands from 30 -> 120pt; 'b' below must be pushed down past its original y0=60
    items = [_item("a", 20, 20, 380, 50, need=120, ro=0),
             _item("b", 20, 60, 380, 90, need=30, ro=1)]
    placements, overflow = _reflow(items, page_h=600, anchored=True)
    assert overflow == []
    assert placements["a"][1] == 140          # 20 + 120
    assert placements["b"][0] > 60            # pushed below its original top
    assert placements["b"][0] >= placements["a"][1]   # sits below the expanded 'a'


def test_overflow_spills_to_next_page():
    # four blocks each needing 120pt on a 300pt page (usable ~264): the first two fit, the rest
    # cascade off the bottom and spill
    items = [_item("a", 20, 20, 380, 50, need=120, ro=0),
             _item("b", 20, 60, 380, 90, need=120, ro=1),
             _item("c", 20, 100, 380, 130, need=120, ro=2),
             _item("d", 20, 140, 380, 170, need=120, ro=3)]
    placements, overflow = _reflow(items, page_h=300, anchored=True)
    assert "a" in placements and "b" in placements
    assert {it["block"].id for it in overflow} == {"c", "d"}
    # the spill page stacks the overflow from the top margin (anchored=False)
    pl2, of2 = _reflow(overflow, page_h=300, anchored=False)
    assert "c" in pl2                              # at least the first overflow block lands


def test_columns_are_independent():
    # left column (x 20-180) and right column (x 220-380); clustering keeps them apart
    items = [_item("L0", 20, 20, 180, 50, need=30, ro=0),
             _item("L1", 20, 60, 180, 90, need=30, ro=1),
             _item("R0", 220, 20, 380, 50, need=30, ro=2)]
    cols = _columns(items)
    assert len(cols) == 2
    ids = sorted(sorted(it["block"].id for it in c) for c in cols)
    assert ids == [["L0", "L1"], ["R0"]]


def test_left_column_expansion_does_not_move_right_column():
    items = [_item("L0", 20, 20, 180, 50, need=200, ro=0),    # expands a lot
             _item("R0", 220, 20, 380, 50, need=30, ro=1)]    # should stay put
    placements, _ = _reflow(items, page_h=600, anchored=True)
    assert placements["R0"] == (20, 50)       # right column untouched by left expansion


def test_end_to_end_spill_grows_page_count(tmp_path):
    src = tmp_path / "s.pdf"
    d = fitz.open()
    d.new_page(width=400, height=300)
    d.save(str(src))
    doc = Document(source_path=str(src), mime="application/pdf", page_count=1)
    doc.page_sizes = {0: (400.0, 300.0)}
    blocks = []
    for i in range(10):
        b = Block(id=f"b{i}", type=BlockType.PARAGRAPH, page=0, text="x", reading_order=i,
                  bbox=BBox(x0=20, y0=20 + i * 26, x1=380, y1=44 + i * 26),
                  style=Style(size=11), confidence=Confidence(source="digital"))
        b.translated = " ".join(["kalimat terjemahan yang panjang sekali"] * 4)
        blocks.append(b)
    doc.blocks = blocks
    out = tmp_path / "o.pdf"
    render_reconstruct(doc, Config(target_lang="id"), str(out))
    assert fitz.open(str(out)).page_count > 1     # expansion spilled onto extra pages
