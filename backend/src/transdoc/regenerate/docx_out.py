"""DOCX renderer (flow fidelity). Rebuilds an editable Word doc from the IR.

Layout = logical structure (headings, paragraphs, lists, tables), not pixel-exact — the
honest trade-off for an *editable* target. For visual fidelity use the PDF overlay renderer.
"""

from __future__ import annotations

from ..config import Config
from ..ir import BlockType, Document, Style


def _align(style: Style):
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    if style.rtl:
        return WD_ALIGN_PARAGRAPH.RIGHT
    return {"center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT,
            "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
            "left": WD_ALIGN_PARAGRAPH.LEFT}.get(style.align)


def _style_runs(para, style: Style) -> None:
    """Apply the IR character style (font/size/weight/colour) to a paragraph's runs — the IR
    captures these but the renderer used to drop them (plain 12pt black). Heading sizes are left
    to the Word style unless the source carried an explicit size."""
    from docx.shared import Pt, RGBColor

    rgb = None
    if style.color and style.color.startswith("#") and len(style.color) == 7:
        try:
            rgb = RGBColor(int(style.color[1:3], 16), int(style.color[3:5], 16),
                           int(style.color[5:7], 16))
        except ValueError:
            rgb = None
    for run in para.runs:
        f = run.font
        if style.bold:
            f.bold = True
        if style.italic:
            f.italic = True
        if style.underline:
            f.underline = True
        if style.font:
            f.name = style.font
        if style.size and style.size > 0:
            f.size = Pt(style.size)
        if rgb is not None:
            f.color.rgb = rgb


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from docx import Document as Docx
    from docx.shared import Inches

    d = Docx()
    for b in doc.ordered_blocks():
        if b.type == BlockType.FIGURE and b.image_path:
            try:
                d.add_picture(b.image_path, width=Inches(5.5))
            except Exception:
                pass
            continue

        # Formula: a verbatim crop (pixel-perfect math) when available, else the LaTeX text.
        if b.type == BlockType.FORMULA and b.image_path:
            try:
                w = (b.bbox.x1 - b.bbox.x0) / 72.0 if b.bbox else 3.0
                d.add_picture(b.image_path, width=Inches(max(0.5, min(5.5, w))))
            except Exception:
                d.add_paragraph(b.output_text.strip())
            continue

        if b.type == BlockType.TABLE and b.table and b.table.rows:
            rows = b.table.rows
            ncols = max(len(r) for r in rows)
            t = d.add_table(rows=len(rows), cols=ncols)
            t.style = "Table Grid"
            for ri, row in enumerate(rows):
                for ci in range(ncols):
                    cell_text = row[ci].output_text if ci < len(row) else ""
                    t.rows[ri].cells[ci].text = cell_text
            d.add_paragraph("")
            continue

        text = b.output_text.strip()
        if not text:
            continue

        # bilingual: source (italic) then translation, mirroring the markdown renderer
        if cfg.bilingual and b.translated is not None and b.text.strip():
            src_p = d.add_paragraph()
            src_p.add_run(b.text.strip()).italic = True
            d.add_paragraph(b.translated.strip())
            continue

        if b.type == BlockType.TITLE:
            p = d.add_heading(text, level=0)
        elif b.type == BlockType.HEADING:
            p = d.add_heading(text, level=max(1, min(9, b.style.heading_level or 1)))
        elif b.type == BlockType.LIST_ITEM:
            p = d.add_paragraph(text, style="List Bullet")
        else:
            p = d.add_paragraph(text)
        # carry the source character styling + alignment into the output (was dropped)
        _style_runs(p, b.style)
        align = _align(b.style)
        if align is not None:
            p.alignment = align

    d.save(out_path)
    return out_path
