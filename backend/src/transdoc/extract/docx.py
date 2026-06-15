"""DOCX extraction via python-docx.

Walks the document body in order, mapping Word styles to IR block types and capturing
tables as structured Table blocks so the renderer can rebuild them faithfully.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Cell, Confidence, Document, Run, Style, Table
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


def _run_color(font) -> str | None:
    try:
        if font.color is not None and font.color.rgb is not None:
            return "#" + str(font.color.rgb)
    except Exception:
        pass
    return None


def _same_style(a: Style, b: Style) -> bool:
    return (a.bold, a.italic, a.underline, a.strike, a.font, a.size, a.color, a.superscript,
            a.subscript) == (b.bold, b.italic, b.underline, b.strike, b.font, b.size, b.color,
                             b.superscript, b.subscript)


def _capture_runs(item) -> list[Run]:
    """Inline runs for a paragraph whose text is NOT uniformly styled (a bold word, a
    superscript ref, ...). Adjacent same-style runs are merged. Returns [] for a uniform
    paragraph so the block-level style path is used unchanged."""
    from .links import paragraph_link
    runs: list[Run] = []
    for r in item.runs:
        if not r.text:
            continue
        f = r.font
        st = Style(bold=bool(f.bold), italic=bool(f.italic), underline=bool(f.underline),
                   strike=bool(f.strike), font=f.name,
                   size=float(f.size.pt) if f.size is not None else None,
                   color=_run_color(f), superscript=bool(f.superscript),
                   subscript=bool(f.subscript))
        if runs and _same_style(runs[-1].style, st):
            runs[-1].text += r.text
        else:
            runs.append(Run(text=r.text, style=st))
    if len(runs) <= 1:
        return []                       # uniform -> block-level handles it
    link = paragraph_link(item)
    if link:                            # a paragraph-level link applies to every run
        for run in runs:
            run.style.link = link
    return runs


def _list_info(item) -> tuple[bool, int]:
    """(ordered, level) for a list paragraph: ordered if the style is a numbered list; level
    from the numbering indent level (ilvl)."""
    ordered = "number" in (item.style.name or "").lower() if item.style else False
    level = 0
    try:
        npr = item._p.pPr.numPr
        if npr is not None and npr.ilvl is not None and npr.ilvl.val is not None:
            level = int(npr.ilvl.val)
    except Exception:
        pass
    return ordered, level


def _para_style(item, level: int) -> Style:
    """Capture the dominant run's character formatting (font name/size/colour/weight) plus
    paragraph alignment — the detail the renderers need to reproduce the original look. Run
    attributes fall back to the paragraph style when a run leaves them inherited (None)."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    name = size = color = None
    bold = italic = underline = strike = False
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
        strike = strike or bool(f.strike)
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

    def _pt(length):
        return float(length.pt) if length is not None else None

    pf = item.paragraph_format
    ls = pf.line_spacing
    return Style(font=name, size=size, bold=bold, italic=italic, underline=underline,
                 strike=strike, color=color, align=align, heading_level=level,
                 space_before=_pt(pf.space_before), space_after=_pt(pf.space_after),
                 line_spacing=float(ls) if isinstance(ls, (int, float)) else None,
                 indent_left=_pt(pf.left_indent), indent_first=_pt(pf.first_line_indent))


def extract(path: str, cfg: Config) -> Document:
    from docx import Document as Docx
    from docx.text.paragraph import Paragraph

    try:
        d = Docx(path)
    except Exception as e:
        raise ValueError(f"unreadable or corrupt DOCX: {e}") from e
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
            if btype == BlockType.LIST_ITEM:
                st.list_ordered, st.list_level = _list_info(item)
            out.blocks.append(
                Block(
                    id=block_id(0, idx),
                    type=btype,
                    text=text,
                    style=st,
                    runs=_capture_runs(item),
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
                    size = bold = None
                    for para in c.paragraphs:
                        for r in para.runs:
                            if r.text.strip():
                                if size is None and r.font.size is not None:
                                    size = float(r.font.size.pt)
                                bold = bold or bool(r.font.bold)
                    cells.append(Cell(text="" if tc in seen_tc else c.text.strip(),
                                      size=size, bold=bool(bold)))
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
