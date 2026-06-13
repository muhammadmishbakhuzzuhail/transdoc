"""render_flow: paginates without crashing and keeps tables (regression guards).

Two bugs lived here: the multi-page loop assumed insert_htmlbox returns leftover HTML
(modern PyMuPDF returns a tuple -> crash), and the empty-text skip dropped TABLE blocks
whose text lives in cells, not output_text.
"""

from __future__ import annotations

import fitz

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Cell, Document, Table
from transdoc.regenerate.pdf_out import render_flow


def _table_block() -> Block:
    rows = [
        [Cell(text="ID", translated="ID"), Cell(text="Name", translated="Nama")],
        [Cell(text="1", translated="1"), Cell(text="Invoice", translated="Faktur")],
    ]
    b = Block(id="t0", type=BlockType.TABLE, page=0, text="")
    b.table = Table(rows=rows)
    return b


def test_render_flow_keeps_table_cells(tmp_path):
    doc = Document(source_path="x.docx", mime="application/x-docx")
    doc.blocks = [
        Block(id="h0", type=BlockType.TITLE, page=0, text="Title", translated="Judul"),
        _table_block(),
    ]
    out = tmp_path / "flow.pdf"
    render_flow(doc, Config(target_lang="id"), str(out))
    assert out.exists()
    text = "".join(p.get_text() for p in fitz.open(str(out)))
    assert "Judul" in text
    assert "Faktur" in text  # a translated table cell survived into the PDF


def test_render_flow_paginates_long_doc(tmp_path):
    # enough paragraphs to overflow one page — must not crash and must span >1 page
    doc = Document(source_path="x.docx", mime="application/x-docx")
    doc.blocks = [
        Block(id=f"p{i}", type=BlockType.PARAGRAPH, page=0,
              text="word " * 80, translated=("kata " * 80))
        for i in range(60)
    ]
    out = tmp_path / "long.pdf"
    render_flow(doc, Config(target_lang="id"), str(out))
    assert fitz.open(str(out)).page_count > 1
