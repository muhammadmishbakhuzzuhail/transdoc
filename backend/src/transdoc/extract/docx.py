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


def _para_style(item, level: int) -> Style:
    """Capture the dominant run's character formatting (font name/size/colour/weight) plus
    paragraph alignment — the detail the renderers need to reproduce the original look. Run
    attributes fall back to the paragraph style when a run leaves them inherited (None)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    name = size = color = None
    bold = italic = underline = False
    for r in (r for r in item.runs if r.text.strip()):
        f = r.font
        if name is None and f.name:
            name = f.name
        if size is None and f.size is not None:
            size = float(f.size.pt)
        if color is None and f.color is not None and f.color.rgb is not None:
            try:
                color = "#" + str(f.color.rgb)
            except Exception:
                pass
        bold = bold or bool(f.bold)
        italic = italic or bool(f.italic)
        underline = underline or bool(f.underline)
    # inherit from the paragraph's named style when runs left things unset
    try:
        sf = item.style.font
        if name is None and sf.name:
            name = sf.name
        if size is None and sf.size is not None:
            size = float(sf.size.pt)
    except Exception:
        pass
    align = {WD_ALIGN_PARAGRAPH.CENTER: "center", WD_ALIGN_PARAGRAPH.RIGHT: "right",
             WD_ALIGN_PARAGRAPH.JUSTIFY: "justify", WD_ALIGN_PARAGRAPH.LEFT: "left"
             }.get(item.alignment) if item.alignment is not None else None
    return Style(font=name, size=size, bold=bold, italic=italic, underline=underline,
                 color=color, align=align, heading_level=level)


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
            from .links import paragraph_link
            st = _para_style(item, level)
            st.link = paragraph_link(item)
            out.blocks.append(
                Block(
                    id=block_id(0, idx),
                    type=btype,
                    text=text,
                    style=st,
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1
        else:  # DocxTable
            # python-docx repeats a merged cell at every grid position it spans (same <w:tc>),
            # which duplicated the text across columns/rows. Blank the continuation positions —
            # the first occurrence keeps the text — so a merged cell's text appears once.
            rows: list[list[Cell]] = []
            seen_tc: set[int] = set()
            for row in item.rows:
                cells: list[Cell] = []
                for c in row.cells:
                    tc = id(c._tc)
                    cells.append(Cell(text="" if tc in seen_tc else c.text.strip()))
                    seen_tc.add(tc)
                rows.append(cells)
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
