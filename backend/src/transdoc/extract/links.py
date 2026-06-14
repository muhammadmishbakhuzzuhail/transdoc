"""Hyperlink capture — populate Block.style.link so links survive translation (audit P1).

PDF: fitz page.get_links() gives URI links with a 'from' rectangle; attach the URI to the
block whose bbox contains the link rect's centre. Block-level (the whole linked block becomes
the link target) — coarse but matches the block-level IR, and most linked text is a distinct
run/paragraph/cell. DOCX hyperlinks are read from python-docx Paragraph.hyperlinks.
"""

from __future__ import annotations


def attach_pdf_links(page, page_blocks) -> None:
    try:
        links = page.get_links()
    except Exception:
        return
    for lk in links:
        uri = lk.get("uri")
        frm = lk.get("from")
        if not uri or frm is None:
            continue
        cx, cy = (frm.x0 + frm.x1) / 2, (frm.y0 + frm.y1) / 2
        for b in page_blocks:
            if not b.bbox or b.style.link:
                continue
            if b.bbox.x0 <= cx <= b.bbox.x1 and b.bbox.y0 <= cy <= b.bbox.y1:
                b.style.link = uri
                break


def paragraph_link(para) -> str | None:
    """First hyperlink address in a python-docx paragraph, if any."""
    try:
        for h in para.hyperlinks:
            if h.address:
                return h.address
    except Exception:
        pass
    return None
