"""Digital PDF table recovery: FLOW output rebuilds a real Table/Cell grid via find_tables;
the LAYOUT overlay path is left on its per-text-block route (no cell tables)."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, OutputFormat  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402


def _table_pdf(path: str) -> None:
    """A page with a ruled 2x3 grid of text cells."""
    doc = fitz.open()
    pg = doc.new_page(width=400, height=300)
    xs = [40, 160, 280, 360]
    ys = [40, 90, 140]
    data = [["Name", "City", "Note"], ["Alice", "London", "First"]]
    for y0, y1, row in zip(ys, ys[1:], data):
        for x0, x1, val in zip(xs, xs[1:], row):
            pg.draw_rect(fitz.Rect(x0, y0, x1, y1))      # ruled cell
            pg.insert_text((x0 + 4, y0 + 20), val, fontsize=11)
    doc.save(path)


def test_flow_recovers_table_grid(tmp_path):
    src = tmp_path / "t.pdf"
    _table_pdf(str(src))
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.MARKDOWN))
    tables = [b for b in doc.blocks if b.type == BlockType.TABLE and b.table]
    assert len(tables) == 1
    rows = tables[0].table.rows
    assert [c.text for c in rows[0]] == ["Name", "City", "Note"]
    assert [c.text for c in rows[1]] == ["Alice", "London", "First"]


def test_layout_keeps_per_block(tmp_path):
    from transdoc.config import Fidelity
    src = tmp_path / "t.pdf"
    _table_pdf(str(src))
    # explicit LAYOUT overlay: cells stay positioned text blocks, no cell-bearing Table block
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.PDF,
                                   fidelity=Fidelity.LAYOUT))
    assert not [b for b in doc.blocks if b.type == BlockType.TABLE and b.table]
    assert any(b.text.strip() for b in doc.blocks)
