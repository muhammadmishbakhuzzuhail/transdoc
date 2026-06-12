"""DOCX extraction via python-docx.

Walks the document body in order, mapping Word styles to IR block types and capturing
tables as structured Table blocks so the renderer can rebuild them faithfully.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Cell, Confidence, Document, Style, Table
from .base import block_id, reflow_order


def iter_block_items(parent):
    """Yield paragraphs and tables in document order (python-docx loses this otherwise).
    Shared with the in-place renderer so extraction and write-back walk the body identically."""
    from docx.oxml.table import CT_Tbl
    from docx.oxml.text.paragraph import CT_P
    from docx.table import Table as DocxTable
    from docx.text.paragraph import Paragraph

    body = parent.element.body
    for child in body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield DocxTable(child, parent)


def _para_type(style_name: str) -> tuple[BlockType, int]:
    s = (style_name or "").lower()
    if s.startswith("title"):
        return BlockType.TITLE, 0
    if s.startswith("heading"):
        lvl = "".join(c for c in s if c.isdigit())
        return BlockType.HEADING, int(lvl) if lvl else 1
    if "list" in s:
        return BlockType.LIST_ITEM, 0
    return BlockType.PARAGRAPH, 0


def extract(path: str, cfg: Config) -> Document:
    from docx import Document as Docx
    from docx.text.paragraph import Paragraph

    d = Docx(path)
    out = Document(source_path=path, mime="docx")
    idx = 0

    for item in iter_block_items(d):
        if isinstance(item, Paragraph):
            text = item.text.strip()
            if not text:
                continue
            btype, level = _para_type(item.style.name if item.style else "")
            runs_bold = any(r.bold for r in item.runs if r.bold)
            out.blocks.append(
                Block(
                    id=block_id(0, idx),
                    type=btype,
                    text=text,
                    style=Style(bold=runs_bold, heading_level=level),
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1
        else:  # DocxTable
            rows: list[list[Cell]] = []
            for row in item.rows:
                rows.append([Cell(text=c.text.strip()) for c in row.cells])
            out.blocks.append(
                Block(
                    id=block_id(0, idx),
                    type=BlockType.TABLE,
                    table=Table(rows=rows, has_header_row=True),
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1

    reflow_order(out)
    return out
