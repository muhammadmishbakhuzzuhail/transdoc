"""PDF renderers.

render_overlay (LAYOUT fidelity) — the differentiator. Reopen the source PDF, redact the
original text at each block's bbox, then place the translation at the SAME bbox via
PyMuPDF insert_htmlbox (HarfBuzz shaping: RTL + complex scripts, auto font substitution).
Output looks like the original with translated text in place.

render_flow (FLOW fidelity) — build a fresh PDF from IR structure when there is no source
geometry (e.g. source was DOCX/image). Uses insert_htmlbox so all scripts render.
"""

from __future__ import annotations

import html

from ..config import Config
from ..ir import BlockType, Document


def _esc(s: str) -> str:
    return html.escape(s)


def render_overlay(doc: Document, cfg: Config, out_path: str) -> str:
    import fitz

    if not doc.source_path or not doc.source_path.lower().endswith(".pdf"):
        raise ValueError("overlay fidelity requires a PDF source")

    pdf = fitz.open(doc.source_path)

    # group translated blocks by page
    by_page: dict[int, list] = {}
    for b in doc.ordered_blocks():
        if b.bbox and b.translated and b.is_translatable:
            by_page.setdefault(b.page, []).append(b)

    for pno, blocks in by_page.items():
        if pno >= pdf.page_count:
            continue
        page = pdf[pno]
        # 1) redact originals
        for b in blocks:
            r = fitz.Rect(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
            page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()
        # 2) overlay translations at original bbox
        for b in blocks:
            r = fitz.Rect(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
            align = "right" if b.style.rtl else "left"
            size = b.style.size or 11
            htmlbox = (f'<div style="font-size:{size:.0f}px;text-align:{align};'
                       f'line-height:1.05">{_esc(b.output_text)}</div>')
            # grow box downward if text overflows; PyMuPDF returns leftover if it doesn't fit
            try:
                page.insert_htmlbox(r, htmlbox)
            except Exception:
                page.insert_textbox(r, b.output_text, fontsize=size, align=0)

    pdf.save(out_path, garbage=4, deflate=True)
    pdf.close()
    return out_path


def render_flow(doc: Document, cfg: Config, out_path: str) -> str:
    import fitz

    pdf = fitz.open()
    page = pdf.new_page()
    width = page.rect.width - 80
    y = 50
    parts: list[str] = []
    for b in doc.ordered_blocks():
        text = _esc(b.output_text.strip())
        if not text:
            continue
        if b.type == BlockType.TITLE:
            parts.append(f"<h1>{text}</h1>")
        elif b.type == BlockType.HEADING:
            lvl = max(2, min(6, b.style.heading_level or 2))
            parts.append(f"<h{lvl}>{text}</h{lvl}>")
        elif b.type == BlockType.LIST_ITEM:
            parts.append(f"<li>{text}</li>")
        elif b.type == BlockType.TABLE and b.table:
            rows = "".join(
                "<tr>" + "".join(f"<td>{_esc(c.output_text)}</td>" for c in row) + "</tr>"
                for row in b.table.rows
            )
            parts.append(f'<table border="1" cellpadding="3">{rows}</table>')
        else:
            parts.append(f"<p>{text}</p>")

    body = f'<div style="font-family:sans-serif">{"".join(parts)}</div>'
    rect = fitz.Rect(40, 40, page.rect.width - 40, page.rect.height - 40)
    # insert_htmlbox returns overflow; add pages until consumed
    spare = body
    while spare:
        leftover = page.insert_htmlbox(rect, spare)
        # PyMuPDF returns (spare_height, scale) or leftover html depending on version;
        # guard against infinite loop by breaking if nothing placed.
        if isinstance(leftover, (int, float)) or not leftover or leftover == spare:
            break
        spare = leftover
        page = pdf.new_page()
    pdf.save(out_path, garbage=4, deflate=True)
    pdf.close()
    return out_path
