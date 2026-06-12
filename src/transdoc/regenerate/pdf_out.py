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

# Effective font size (pt) below which overlaid text is too small to read. We don't silently
# ship illegibly-shrunk text — we flag it so the report can count and surface it.
LEGIBLE_MIN_PT = 6.0

# OCR below this confidence is unreliable (garbage); don't cover the original with it.
OCR_OVERLAY_MIN = 0.5


def _ocr_garbage(b) -> bool:
    return b.confidence.ocr is not None and b.confidence.ocr < OCR_OVERLAY_MIN

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

    def _is_vertical(b) -> bool:
        # Rotated/vertical text (e.g. an arXiv ID sidebar) lives in a tall, very narrow box.
        # Redacting it and dropping horizontal text in there shrinks the translation to an
        # illegible sliver, so leave such blocks untouched (they're usually identifiers).
        r = _block_rect(b)
        return r.width < 40 and r.height > r.width * 4

    # group translated blocks by page (skip vertical/rotated text — keep the original)
    by_page: dict[int, list] = {}
    for b in doc.ordered_blocks():
        if b.bbox and b.translated and b.is_translatable:
            if _is_vertical(b):
                b.flags["rotated_text"] = "vertical/rotated text left untranslated (verify)"
                continue
            if _ocr_garbage(b):
                b.flags["ocr_unreliable"] = (
                    f"OCR {b.confidence.ocr:.0%} — left original, not overlaid")
                continue
            by_page.setdefault(b.page, []).append(b)

    try:
        for pno, blocks in by_page.items():
            if pno >= pdf.page_count:
                continue
            page = pdf[pno]
            # 1) redact ONLY the source text, leaving images + vector art in place. A logo or
            #    coloured box behind the text (page background) is preserved instead of being
            #    punched out by an opaque white fill.
            for b in blocks:
                r = _block_rect(b)
                page.add_redact_annot(r)  # no fill -> keep whatever is behind the text
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,        # don't touch background logos/images
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,   # keep rule lines / table borders
                text=fitz.PDF_REDACT_TEXT_REMOVE,         # remove only the original glyphs
            )
            # Obstacles for box growth: every block with a bbox on this page (not just the
            # translated ones) so we never grow a box over a figure, formula, or neighbour.
            obstacles = [_block_rect(x) for x in doc.ordered_blocks()
                         if x.page == pno and x.bbox]

            def _grow_down(r, obstacles=obstacles, page=page):
                """Grow the box down into the empty space before the next block below (or the
                page edge), so expanded text keeps its font size instead of being shrunk."""
                limit = page.rect.height
                for o in obstacles:
                    if o.y0 >= r.y1 - 1 and min(r.x1, o.x1) - max(r.x0, o.x0) > 2:
                        limit = min(limit, o.y0)
                new_y1 = limit - 2.0
                return fitz.Rect(r.x0, r.y0, r.x1, new_y1) if new_y1 > r.y1 + 1 else r

            # 2) overlay translations at original bbox, auto-fitting expanded text: first grow
            #    the box into adjacent whitespace (keeps font size), then insert_htmlbox shrinks
            #    only if still needed; a hard shrink is flagged for human review.
            for b in blocks:
                r = _grow_down(_block_rect(b))
                rtl = b.style.rtl
                size = b.style.size or 11
                if _is_mixed_bidi(b.output_text):
                    b.flags["bidi_mixed"] = (
                        "mixed RTL+LTR on one line — insert_htmlbox may misorder words; verify")
                # Preserve source justification: body paragraphs flush both margins (justify),
                # headings/short runs keep their natural edge.
                is_heading = b.type in (BlockType.TITLE, BlockType.HEADING)
                if not is_heading and len(b.output_text) > 40:
                    align = "justify"
                else:
                    align = "right" if rtl else "left"
                dir_css = "direction:rtl;" if rtl else ""
                # Carry the source character styling so the translation looks like the original.
                weight_css = "font-weight:bold;" if b.style.bold else ""
                italic_css = "font-style:italic;" if b.style.italic else ""
                color_css = f"color:{b.style.color};" if b.style.color else ""
                htmlbox = (f'<div style="{dir_css}{weight_css}{italic_css}{color_css}'
                           f'font-size:{size:.0f}px;text-align:{align};'
                           f'line-height:1.05">{_esc(b.output_text)}</div>')
                try:
                    # scale_low=0 lets PyMuPDF shrink text down to fit; returns (spare, scale)
                    ret = page.insert_htmlbox(r, htmlbox, scale_low=0)
                    scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
                    effective = (size or 11) * (scale or 1.0)
                    if effective < LEGIBLE_MIN_PT:
                        # honest: the translation only fit by shrinking below readable size
                        b.flags["illegible"] = (
                            f"rendered at {effective:.1f}pt (< {LEGIBLE_MIN_PT:.0f}pt) — "
                            f"too small to read; box too tight for the translation")
                    elif scale and scale < OVERFLOW_FLAG_SCALE:
                        b.flags["text_expansion"] = (
                            f"shrunk to {scale:.0%} to fit box — verify legibility/layout")
                except Exception:
                    page.insert_textbox(r, b.output_text, fontsize=size, align=0)

        # If only some pages were selected (--pages), the overlay covered just those; the rest
        # are still untranslated original. Drop them so the output isn't a translated/source mix.
        _subset_pages(pdf, cfg)
        pdf.save(out_path, garbage=4, deflate=True)
    finally:
        pdf.close()
    return out_path


def _subset_pages(pdf, cfg) -> None:
    """Keep only the pages named by cfg.pages (1-based spec). No-op when unset/all."""
    from ..extract.pdf import _parse_pages
    sel = _parse_pages(getattr(cfg, "pages", None), pdf.page_count)
    if sel is not None and len(sel) < pdf.page_count:
        pdf.select(sorted(sel))


def render_image_overlay(doc: Document, cfg: Config, out_path: str) -> str:
    """LAYOUT fidelity for a photo/image source (jpg/png) — the Google-Lens-style path.

    Keep the original image as the page background, cover each OCR'd text region, and place
    the translation at that same spot. OCR bboxes are in the image's native pixels; opening
    the image as a PyMuPDF document maps 1 pixel -> 1 point, so the bboxes apply 1:1.
    """
    import fitz
    from PIL import Image as _PILImage

    # Nothing reliable to overlay (no translatable text, or OCR is garbage) -> return the
    # source untouched instead of covering it with low-confidence gibberish or re-encoding.
    overlay = [b for b in doc.ordered_blocks()
               if b.bbox and b.translated and b.is_translatable and not _ocr_garbage(b)]
    if not overlay:
        ext = out_path.lower().rsplit(".", 1)[-1]
        src_ext = (doc.source_path or "").lower().rsplit(".", 1)[-1]
        if ext == src_ext:
            import shutil
            shutil.copyfile(doc.source_path, out_path)
            return out_path
        # different target format: re-encode without any overlay
        _PILImage.open(doc.source_path).convert("RGB").save(out_path)
        return out_path

    # Overlay on the deskewed copy when one exists (its geometry matches the OCR bboxes so
    # the translation lands straight and in-place); otherwise the original image.
    bg = doc.render_path or doc.source_path

    # Build the page at the image's exact PIXEL size so OCR bboxes (raw pixels) map 1 px ->
    # 1 pt. (Opening the image directly and letting fitz interpret DPI metadata would scale
    # the page by 72/dpi and misplace every box on any image not tagged at 72 dpi.)
    with _PILImage.open(bg) as _im:
        iw, ih = _im.size
    pdf = fitz.open()
    try:
        page = pdf.new_page(width=iw, height=ih)
        page.insert_image(fitz.Rect(0, 0, iw, ih), filename=bg)

        for b in doc.ordered_blocks():
            if not (b.bbox and b.translated and b.is_translatable) or _ocr_garbage(b):
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
                effective = (size or 11) * (scale or 1.0)
                if effective < LEGIBLE_MIN_PT:
                    b.flags["illegible"] = (
                        f"rendered at {effective:.1f}pt (< {LEGIBLE_MIN_PT:.0f}pt) — too small")
                elif scale and scale < OVERFLOW_FLAG_SCALE:
                    b.flags["text_expansion"] = (
                        f"shrunk to {scale:.0%} to fit box — verify legibility/layout")
            except Exception:
                page.insert_textbox(r, b.output_text, fontsize=11, align=0)

        # Output a translated image when the target is an image (the natural Lens-style
        # result: upload a photo, get the photo back translated), else an image-backed PDF.
        ext = out_path.lower().rsplit(".", 1)[-1]
        if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"):
            page.get_pixmap().save(out_path)   # identity matrix -> original pixel dimensions
        else:
            pdf.save(out_path, garbage=4, deflate=True)
    finally:
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
    try:
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
    finally:
        pdf.close()
    return out_path


def _flow_style(b) -> str:
    """Inline CSS carrying the block's captured styling into the reflow."""
    s: list[str] = []
    if b.style.bold:
        s.append("font-weight:bold")
    if b.style.italic:
        s.append("font-style:italic")
    if b.style.color and b.style.color.lower() not in ("#000000", "#000"):
        s.append(f"color:{b.style.color}")
    if b.style.align in ("center", "right", "justify"):
        s.append(f"text-align:{b.style.align}")
    return ";".join(s)


def render_flow(doc: Document, cfg: Config, out_path: str) -> str:
    import os

    import fitz

    # Build an image archive so embedded figures can be reflowed back in (referenced by base
    # name in <img src=...>). Without this the reconstruction would silently drop every image.
    archive = fitz.Archive()
    img_names: dict[str, str] = {}
    for b in doc.ordered_blocks():
        if b.type == BlockType.FIGURE and b.image_path and os.path.exists(b.image_path):
            d = os.path.dirname(b.image_path)
            try:
                archive.add(d)
            except Exception:
                continue
            img_names[b.id] = os.path.basename(b.image_path)

    parts: list[str] = []
    open_list = False

    def _close_list():
        nonlocal open_list
        if open_list:
            parts.append("</ul>")
            open_list = False

    for b in doc.ordered_blocks():
        if b.type != BlockType.LIST_ITEM:
            _close_list()

        if b.type == BlockType.FIGURE:
            name = img_names.get(b.id)
            if name:
                parts.append(f'<p><img src="{name}" style="max-width:90%"></p>')
            continue
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
        style = _flow_style(b)
        attr = f' style="{style}"' if style else ""
        if b.type == BlockType.TITLE:
            parts.append(f"<h1{attr}>{text}</h1>")
        elif b.type == BlockType.HEADING:
            lvl = max(2, min(6, b.style.heading_level or 2))
            parts.append(f"<h{lvl}{attr}>{text}</h{lvl}>")
        elif b.type == BlockType.LIST_ITEM:
            if not open_list:
                parts.append("<ul>")
                open_list = True
            parts.append(f"<li{attr}>{text}</li>")
        else:
            parts.append(f"<p{attr}>{text}</p>")
    _close_list()

    body = f'<div style="font-family:sans-serif">{"".join(parts)}</div>'

    # Paginate with fitz.Story: it flows arbitrary-length HTML across as many pages as
    # needed. (The old insert_htmlbox loop assumed the call returns leftover HTML; modern
    # PyMuPDF returns a (spare_height, scale) tuple instead, which broke multi-page output.)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (40, 40, -40, -40)
    story = fitz.Story(html=body, archive=archive)
    writer = fitz.DocumentWriter(out_path)
    try:
        more = 1
        while more:
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
    finally:
        writer.close()      # always close so the output isn't left truncated on error
    return out_path
