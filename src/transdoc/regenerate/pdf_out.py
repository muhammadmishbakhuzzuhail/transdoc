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
import re

from ..config import Config
from ..ir import BlockType, Document


# Below this shrink factor, the box was too small for the translation -> flag for review.
OVERFLOW_FLAG_SCALE = 0.6

# RTL scripts: Hebrew, Arabic (+ supplements/presentation forms). insert_htmlbox shapes each
# script via HarfBuzz but does NOT correctly order a single line that MIXES RTL + LTR runs
# (PyMuPDF maintainer, discussion #3022). We can't fix it here, so we flag it for review.
_RTL_RE = re.compile(r"[֐-׿؀-ۿݐ-ݿࢠ-ࣿיִ-﷿ﹰ-﻿]")
_LATIN_RE = re.compile(r"[A-Za-z]")


def _is_mixed_bidi(s: str) -> bool:
    return bool(_RTL_RE.search(s) and _LATIN_RE.search(s))


def _esc(s: str) -> str:
    return html.escape(s)


def render_overlay(doc: Document, cfg: Config, out_path: str) -> str:
    import fitz

    if not doc.source_path or not doc.source_path.lower().endswith(".pdf"):
        raise ValueError("overlay fidelity requires a PDF source")

    pdf = fitz.open(doc.source_path)

    def _block_rect(b) -> "fitz.Rect":
        # OCR blocks carry bbox in 300-dpi pixels (the page was rasterized for OCR); digital
        # blocks are already in PDF points. Scale OCR boxes back to points so the redaction +
        # overlay land on the original geometry instead of off-page.
        s = 72.0 / 300.0 if b.confidence.source == "ocr" else 1.0
        return fitz.Rect(b.bbox.x0 * s, b.bbox.y0 * s, b.bbox.x1 * s, b.bbox.y1 * s)

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
            r = _block_rect(b)
            page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()
        # 2) overlay translations at original bbox, auto-fitting expanded text.
        #    Translation often expands (+20-30% EN->ID). insert_htmlbox(scale_low=0)
        #    shrinks the text to fit the original box and returns the scale factor;
        #    if it had to shrink hard, we flag the block for human review.
        for b in blocks:
            r = _block_rect(b)
            rtl = b.style.rtl
            size = b.style.size or 11
            if _is_mixed_bidi(b.output_text):
                b.flags["bidi_mixed"] = (
                    "mixed RTL+LTR on one line — insert_htmlbox may misorder words; verify")
            # Preserve source justification: body paragraphs flush both margins (justify),
            # headings/short runs keep their natural edge. Stretching a single short line
            # looks wrong, so only justify text long enough to wrap.
            is_heading = b.type in (BlockType.TITLE, BlockType.HEADING)
            if not is_heading and len(b.output_text) > 40:
                align = "justify"
            else:
                align = "right" if rtl else "left"
            dir_css = "direction:rtl;" if rtl else ""
            htmlbox = (f'<div style="{dir_css}font-size:{size:.0f}px;text-align:{align};'
                       f'line-height:1.05">{_esc(b.output_text)}</div>')
            try:
                # scale_low=0 lets PyMuPDF shrink text down to fit; returns (spare, scale)
                ret = page.insert_htmlbox(r, htmlbox, scale_low=0)
                scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
                if scale and scale < OVERFLOW_FLAG_SCALE:
                    b.flags["text_expansion"] = (
                        f"shrunk to {scale:.0%} to fit box — verify legibility/layout")
            except Exception:
                page.insert_textbox(r, b.output_text, fontsize=size, align=0)

    pdf.save(out_path, garbage=4, deflate=True)
    pdf.close()
    return out_path


def render_image_overlay(doc: Document, cfg: Config, out_path: str) -> str:
    """LAYOUT fidelity for a photo/image source (jpg/png) — the Google-Lens-style path.

    Keep the original image as the page background, cover each OCR'd text region, and place
    the translation at that same spot. OCR bboxes are in the image's native pixels; opening
    the image as a PyMuPDF document maps 1 pixel -> 1 point, so the bboxes apply 1:1.
    """
    import fitz
    from PIL import Image as _PILImage

    # Overlay on the deskewed copy when one exists (its geometry matches the OCR bboxes so
    # the translation lands straight and in-place); otherwise the original image.
    bg = doc.render_path or doc.source_path

    # Build the page at the image's exact PIXEL size so OCR bboxes (raw pixels) map 1 px ->
    # 1 pt. (Opening the image directly and letting fitz interpret DPI metadata would scale
    # the page by 72/dpi and misplace every box on any image not tagged at 72 dpi.)
    with _PILImage.open(bg) as _im:
        iw, ih = _im.size
    pdf = fitz.open()
    page = pdf.new_page(width=iw, height=ih)
    page.insert_image(fitz.Rect(0, 0, iw, ih), filename=bg)

    for b in doc.ordered_blocks():
        if not (b.bbox and b.translated and b.is_translatable):
            continue
        r = fitz.Rect(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
        # cover the original text so the translation reads cleanly over the photo. Pad the
        # box a little (OCR boxes hug the glyphs, leaving ascenders/descenders peeking) and
        # use an opaque fill so the source text can't bleed through behind the translation.
        pad = max(2.0, r.height * 0.2)
        cover = fitz.Rect(r.x0 - 2, r.y0 - pad, r.x1 + 2, r.y1 + pad)
        page.draw_rect(cover, color=None, fill=(1, 1, 1), fill_opacity=1.0)
        if _is_mixed_bidi(b.output_text):
            b.flags["bidi_mixed"] = (
                "mixed RTL+LTR on one line — insert_htmlbox may misorder words; verify")
        rtl = b.style.rtl
        size = b.style.size or max(8.0, r.height * 0.7)
        align = "right" if rtl else "left"
        dir_css = "direction:rtl;" if rtl else ""
        htmlbox = (f'<div style="{dir_css}font-size:{size:.0f}px;text-align:{align};'
                   f'line-height:1.05">{_esc(b.output_text)}</div>')
        try:
            ret = page.insert_htmlbox(r, htmlbox, scale_low=0)
            scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
            if scale and scale < OVERFLOW_FLAG_SCALE:
                b.flags["text_expansion"] = (
                    f"shrunk to {scale:.0%} to fit box — verify legibility/layout")
        except Exception:
            page.insert_textbox(r, b.output_text, fontsize=11, align=0)

    # Output a translated image when the target is an image (the natural Lens-style result:
    # upload a photo, get the photo back translated), else an image-backed PDF.
    ext = out_path.lower().rsplit(".", 1)[-1]
    if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"):
        pix = page.get_pixmap()  # identity matrix -> original pixel dimensions
        pdf.close()
        pix.save(out_path)
    else:
        pdf.save(out_path, garbage=4, deflate=True)
        pdf.close()
    return out_path


def render_searchable(doc: Document, cfg: Config, out_path: str) -> str:
    """Add an invisible OCR text layer over the original scanned PDF -> searchable PDF.

    Like OCRmyPDF: keeps the page image untouched and overlays selectable, invisible text
    (render_mode 3) at each OCR block's bbox. Uses SOURCE text (no translation). Requires a
    PDF source whose pages were OCR'd into the IR.
    """
    import fitz

    if not doc.source_path or not doc.source_path.lower().endswith(".pdf"):
        raise ValueError("searchable output requires a PDF source")
    pdf = fitz.open(doc.source_path)
    for b in doc.ordered_blocks():
        if not (b.bbox and b.text.strip() and b.confidence.source == "ocr"):
            continue
        if b.page >= pdf.page_count:
            continue
        page = pdf[b.page]
        # OCR bbox is in pixels at 300 dpi (see extractor); scale to PDF points (72 dpi).
        s = 72.0 / 300.0
        r = fitz.Rect(b.bbox.x0 * s, b.bbox.y0 * s, b.bbox.x1 * s, b.bbox.y1 * s)
        # fit fontsize to the box (text is invisible, so just needs to land inside it)
        size = max(4.0, min(r.height, r.width / max(1, len(b.text)) * 1.8))
        try:
            for _ in range(6):
                ret = page.insert_textbox(r, b.text, fontsize=size, render_mode=3)
                if ret >= 0 or size <= 4:
                    break
                size *= 0.7  # shrink until the text fits the original bbox
        except Exception:
            continue
    pdf.save(out_path, garbage=4, deflate=True)
    pdf.close()
    return out_path


def render_flow(doc: Document, cfg: Config, out_path: str) -> str:
    import fitz

    parts: list[str] = []
    for b in doc.ordered_blocks():
        # Tables carry their text in cells, not output_text — handle before the empty-text
        # skip below, or the whole table gets dropped.
        if b.type == BlockType.TABLE and b.table:
            # fitz.Story ignores the HTML `border` attribute; draw the grid with CSS instead.
            cell = "border:1px solid #000;padding:3px"
            rows = "".join(
                "<tr>" + "".join(
                    f'<td style="{cell}">{_esc(c.output_text)}</td>' for c in row) + "</tr>"
                for row in b.table.rows
            )
            parts.append(
                f'<table style="border-collapse:collapse;border:1px solid #000">'
                f'{rows}</table>')
            continue
        text = _esc(b.output_text.strip())
        if not text:
            continue
        # bilingual: source (muted italic) then translation, mirroring the other renderers
        if cfg.bilingual and b.translated is not None and b.text.strip():
            parts.append(
                f'<p style="color:#888;font-style:italic">{_esc(b.text.strip())}</p>')
            parts.append(f"<p>{_esc(b.translated.strip())}</p>")
            continue
        if b.type == BlockType.TITLE:
            parts.append(f"<h1>{text}</h1>")
        elif b.type == BlockType.HEADING:
            lvl = max(2, min(6, b.style.heading_level or 2))
            parts.append(f"<h{lvl}>{text}</h{lvl}>")
        elif b.type == BlockType.LIST_ITEM:
            parts.append(f"<li>{text}</li>")
        else:
            parts.append(f"<p>{text}</p>")

    body = f'<div style="font-family:sans-serif">{"".join(parts)}</div>'

    # Paginate with fitz.Story: it flows arbitrary-length HTML across as many pages as
    # needed. (The old insert_htmlbox loop assumed the call returns leftover HTML; modern
    # PyMuPDF returns a (spare_height, scale) tuple instead, which broke multi-page output.)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    story = fitz.Story(html=body)
    writer = fitz.DocumentWriter(out_path)
    more = 1
    while more:
        dev = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return out_path
