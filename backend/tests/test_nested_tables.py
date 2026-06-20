# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Nested tables: a table inside a cell — captured, translated (recursive), rendered."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import Cell, Table


def _nested_doc():
    from transdoc.ir import BBox, Block, BlockType, Confidence, Document
    inner = Table(rows=[[Cell(text="inner a"), Cell(text="inner b")]])
    outer = Table(rows=[[Cell(text="outer"), Cell(table=inner)]])
    d = Document(source_path="x", mime="docx")
    d.blocks = [Block(id="t", type=BlockType.TABLE, bbox=BBox(x0=0,y0=0,x1=1,y1=1),
                      table=outer, confidence=Confidence())]
    return d


def test_pdf_nested_table_html():
    from transdoc.regenerate.pdf_out import _table_html
    html = _table_html(_nested_doc().blocks[0].table)
    assert html.count("<table") == 2 and "inner a" in html   # nested table emitted


def test_translate_collects_nested_cells():
    from transdoc.translate.base import _collect_cells
    items = []
    _collect_cells(_nested_doc().blocks[0].table, items)
    texts = [t for t, _ in items]
    assert "outer" in texts and "inner a" in texts and "inner b" in texts


def test_docx_extract_nested_table(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    from transdoc.ir import BlockType
    dd = docx.Document()
    t = dd.add_table(rows=1, cols=1)
    inner = t.cell(0, 0).add_table(1, 2)
    inner.cell(0, 0).text = "nx"
    inner.cell(0, 1).text = "ny"
    p = tmp_path / "n.docx"
    dd.save(str(p))
    blk = next(b for b in extract(str(p), Config(target_lang="id")).blocks
               if b.type == BlockType.TABLE)
    assert blk.table.rows[0][0].table is not None


def test_docx_table_cells_not_blanked_under_gc(tmp_path):
    """Regression: _build_table keyed merge-continuation detection on id(c._tc). lxml hands out
    throwaway proxy objects, so a freed proxy's id() gets recycled by an unrelated <w:tc> and a
    later unique cell collided with an earlier id() -> silently blanked. GC-pressure dependent, so
    force aggressive GC over a sizeable un-merged table: every cell text MUST survive."""
    import gc

    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import _build_table

    dd = docx.Document()
    t = dd.add_table(rows=30, cols=4)            # no merged cells anywhere
    for ri, row in enumerate(t.rows):
        for ci, c in enumerate(row.cells):
            c.text = f"r{ri}c{ci}"
    p = tmp_path / "big.docx"
    dd.save(str(p))

    old = gc.get_threshold()
    gc.set_threshold(1, 1, 1)                     # maximise proxy churn / id recycling
    try:
        d2 = docx.Document(str(p))
        tbl = _build_table(d2.tables[0])
    finally:
        gc.set_threshold(*old)

    blanked = [(ri, ci) for ri, row in enumerate(tbl.rows)
               for ci, cell in enumerate(row) if not cell.text]
    assert blanked == [], f"un-merged cells wrongly blanked: {blanked}"


def test_docx_merged_cells_blanked(tmp_path):
    """Genuine merges (horizontal gridSpan + vertical merge) still blank their continuation cells."""
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import _build_table

    dd = docx.Document()
    t = dd.add_table(rows=3, cols=3)
    for ri, row in enumerate(t.rows):
        for ci, c in enumerate(row.cells):
            c.text = f"r{ri}c{ci}"
    t.cell(0, 0).merge(t.cell(0, 1))             # horizontal
    t.cell(0, 2).merge(t.cell(1, 2))             # vertical
    p = tmp_path / "m.docx"
    dd.save(str(p))
    tbl = _build_table(docx.Document(str(p)).tables[0])
    assert tbl.rows[0][1].text == ""             # horizontal-merge continuation blanked
    assert tbl.rows[1][2].text == ""             # vertical-merge continuation blanked
    assert tbl.rows[2][0].text and tbl.rows[2][2].text   # unrelated cells intact


def test_docx_render_nested(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.regenerate.docx_out import render
    out = tmp_path / "o.docx"
    render(_nested_doc(), Config(target_lang="id"), str(out))
    dd = docx.Document(str(out))
    outer = dd.tables[0]                          # document.tables lists top-level only
    nested = outer.cell(0, 1).tables             # nested table lives inside the cell
    assert len(nested) == 1 and "inner a" in nested[0].cell(0, 0).text
