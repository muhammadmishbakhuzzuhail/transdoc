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


def _apply_pdf_metadata(pdf, doc) -> None:
    """Carry the source document metadata (title/author/subject/keywords/creator) onto the
    output PDF — captured in extract but previously not written out."""
    md = getattr(doc, "metadata", None)
    if not md:
        return
    keep = {k: md[k] for k in ("title", "author", "subject", "keywords", "creator")
            if md.get(k)}
    if keep:
        try:
            pdf.set_metadata(keep)
        except Exception:
            pass


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
                ul_css = "text-decoration:underline;" if b.style.underline else ""
                color_css = f"color:{b.style.color};" if b.style.color else ""
                _inner = _runs_html(b.runs) if b.runs else _esc(b.output_text)
                if b.style.link and not b.runs:
                    _inner = f'<a href="{_esc(b.style.link)}">{_inner}</a>'
                htmlbox = (f'<div style="{dir_css}{weight_css}{italic_css}{ul_css}{color_css}'
                           f'font-size:{size:.0f}px;text-align:{align};'
                           f'line-height:1.05">{_inner}</div>')
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
        _apply_pdf_metadata(pdf, doc)
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
    # Carry the real source font size (in points) so the reflow keeps the document's size
    # hierarchy — title 20pt / heading 14pt / body 11pt — instead of collapsing everything to
    # the HTML element defaults (<p>=12, <h1>=18).
    if b.style.size and b.style.size > 0:
        s.append(f"font-size:{b.style.size:.1f}pt")
    if b.style.font:
        s.append(f"font-family:{b.style.font}")
    if b.style.bold:
        s.append("font-weight:bold")
    if b.style.italic:
        s.append("font-style:italic")
    if b.style.underline:
        s.append("text-decoration:underline")
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
            # per-cell size/weight/align + row/col span; CSS grid (fitz.Story ignores `border`).
            parts.append(_table_html(b.table.rows))
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


def _cell_td(c) -> str:
    """One <td> honoring the cell's font size, weight, alignment and row/col span (was a fixed
    8pt with spans ignored)."""
    style = ["border:1px solid #000", "padding:2px",
             f"font-size:{c.size:.0f}pt" if c.size and c.size > 0 else "font-size:8pt"]
    if c.bold:
        style.append("font-weight:bold")
    if c.align in ("center", "right"):
        style.append(f"text-align:{c.align}")
    span = ""
    if c.colspan > 1:
        span += f' colspan="{c.colspan}"'
    if c.rowspan > 1:
        span += f' rowspan="{c.rowspan}"'
    return f'<td style="{";".join(style)}"{span}>{_esc(c.output_text)}</td>'


def _table_html(rows) -> str:
    body = "".join("<tr>" + "".join(_cell_td(c) for c in row) + "</tr>" for row in rows)
    return f'<table style="border-collapse:collapse;border:1px solid #000">{body}</table>'


def _norm_rect(b):
    """Block bbox -> PDF points. OCR blocks carry 300-dpi pixels (page was rasterised); digital
    blocks are already in points."""
    import fitz
    s = 72.0 / 300.0 if b.confidence.source == "ocr" else 1.0
    bb = b.bbox
    return fitz.Rect(bb.x0 * s, bb.y0 * s, bb.x1 * s, bb.y1 * s)


def _grow_rect(r, obstacles, page_height):
    """Grow a box down into the empty space before the next block (or page edge)."""
    import fitz
    limit = page_height
    for o in obstacles:
        if o.y0 >= r.y1 - 1 and min(r.x1, o.x1) - max(r.x0, o.x0) > 2:
            limit = min(limit, o.y0)
    new_y1 = limit - 2.0
    return fitz.Rect(r.x0, r.y0, r.x1, new_y1) if new_y1 > r.y1 + 1 else r


def _run_span(run) -> str:
    """One inline run -> styled <span> (bold/italic/underline/super/sub/colour/link)."""
    s = run.style
    css = []
    if s.bold:
        css.append("font-weight:bold")
    if s.italic:
        css.append("font-style:italic")
    deco = (["underline"] if s.underline else []) + (["line-through"] if s.strike else [])
    if deco:
        css.append("text-decoration:" + " ".join(deco))
    if s.superscript:
        css.append("vertical-align:super;font-size:smaller")
    elif s.subscript:
        css.append("vertical-align:sub;font-size:smaller")
    if s.color and s.color.lower() not in ("#000000", "#000"):
        css.append(f"color:{s.color}")
    inner = _esc(run.output_text)
    if s.link:
        inner = f'<a href="{_esc(s.link)}">{inner}</a>'
    return f'<span style="{";".join(css)}">{inner}</span>' if css else inner


def _runs_html(runs) -> str:
    return "".join(_run_span(r) for r in runs)


def _block_html(b):
    """Styled HTML for a block (size/bold/italic/colour/align/rtl) -> (html, size_pt)."""
    size = b.style.size or 11
    rtl = b.style.rtl
    is_heading = b.type in (BlockType.TITLE, BlockType.HEADING)
    if b.style.align in ("center", "right", "justify"):
        align = b.style.align
    elif not is_heading and len(b.output_text) > 40:
        align = "right" if rtl else "justify"
    else:
        align = "right" if rtl else "left"
    css = [f"font-size:{size:.1f}pt", f"text-align:{align}", "line-height:1.05"]
    if b.style.font:
        css.append(f"font-family:{b.style.font}")
    if rtl:
        css.append("direction:rtl")
    if b.style.bold:
        css.append("font-weight:bold")
    if b.style.italic:
        css.append("font-style:italic")
    _deco = (["underline"] if b.style.underline else []) + (["line-through"] if b.style.strike
                                                            else [])
    if _deco:
        css.append("text-decoration:" + " ".join(_deco))
    if b.style.color and b.style.color.lower() not in ("#000000", "#000"):
        css.append(f"color:{b.style.color}")
    if b.style.space_before:
        css.append(f"margin-top:{b.style.space_before:.0f}pt")
    if b.style.space_after:
        css.append(f"margin-bottom:{b.style.space_after:.0f}pt")
    if b.style.indent_left:
        css.append(f"margin-left:{b.style.indent_left:.0f}pt")
    if b.style.indent_first:
        css.append(f"text-indent:{b.style.indent_first:.0f}pt")
    if b.style.line_spacing and b.style.line_spacing > 0:
        css = [c for c in css if not c.startswith("line-height")]
        css.append(f"line-height:{b.style.line_spacing:.2f}")
    inner = _runs_html(b.runs) if b.runs else _esc(b.output_text)
    if b.style.link and not b.runs:
        inner = f'<a href="{_esc(b.style.link)}">{inner}</a>'
    return f'<div style="{";".join(css)}">{inner}</div>', size


def _hex_rgb(h):
    if not h:
        return None
    h = h.lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return None


def _redraw_vectors(page, drawings) -> None:
    """Redraw captured line-art (lines/rects, PDF points) on a reconstructed page so rules,
    dividers, field underlines and boxes survive — the reconstruct renderer would otherwise
    drop every vector. Best-effort; a bad shape is skipped, never fatal."""
    import fitz

    for d in drawings or []:
        try:
            w = float(d.get("width") or 0.6)
            if d.get("kind") == "curve":
                p = [fitz.Point(x, y) for x, y in d.get("points", [])]
                if len(p) == 4:
                    page.draw_bezier(p[0], p[1], p[2], p[3],
                                     color=_hex_rgb(d.get("color")) or (0, 0, 0), width=w)
            elif d.get("kind") == "line":
                page.draw_line(fitz.Point(d["x0"], d["y0"]), fitz.Point(d["x1"], d["y1"]),
                               color=_hex_rgb(d.get("color")) or (0, 0, 0), width=w)
            elif d.get("kind") == "rect":
                page.draw_rect(fitz.Rect(d["x0"], d["y0"], d["x1"], d["y1"]),
                               color=_hex_rgb(d.get("color")), fill=_hex_rgb(d.get("fill")),
                               width=w)
        except Exception:
            continue


def render_reconstruct(doc: Document, cfg: Config, out_path: str) -> str:
    """Positioned per-page reconstruction — the DeepL approach. A fresh page at the SOURCE page
    size for every source page, with each block's translation placed at its ORIGINAL bbox and
    reflowed within it; figures go back at their original position. Preserves page count, page
    size, block positions and images — only the text changes. Dense boxes grow into adjacent
    whitespace, then shrink to fit (flagged 'illegible' below the readable floor)."""
    import fitz

    by_page: dict[int, list] = {}
    for b in doc.ordered_blocks():
        by_page.setdefault(b.page, []).append(b)
    npages = doc.page_count or ((max(by_page) + 1) if by_page else 1)

    # Keep the source open to crop formula regions as images (math notation — fractions,
    # super/subscripts — is flattened by get_text, so it can't be re-typeset; crop it verbatim
    # like BabelDOC/DeepL do).
    src = None
    if doc.source_path and doc.source_path.lower().endswith(".pdf"):
        try:
            src = fitz.open(doc.source_path)
        except Exception:
            src = None

    out = fitz.open()
    try:
        for pno in range(npages):
            w, h = doc.page_sizes.get(pno, (595.0, 842.0))
            page = out.new_page(width=w, height=h)
            _redraw_vectors(page, doc.page_drawings.get(pno, []))
            blocks = by_page.get(pno, [])
            obstacles = [_norm_rect(b) for b in blocks if b.bbox]
            for b in blocks:
                if not b.bbox:
                    continue
                r = _norm_rect(b)
                if b.type == BlockType.FIGURE:
                    if b.crop_region and src is not None and b.page < src.page_count:
                        # layout-detected non-text region (figure/diagram/chart/math/table):
                        # crop it verbatim from the source -> pixel-perfect, never re-typeset.
                        try:
                            page.insert_image(r, pixmap=src[b.page].get_pixmap(clip=r, dpi=200))
                        except Exception:
                            pass
                    elif b.image_path:
                        try:
                            page.insert_image(r, filename=b.image_path)
                        except Exception:
                            pass
                    continue
                if b.type == BlockType.FORMULA and src is not None and b.page < src.page_count:
                    # crop the equation region from the source (pixel-perfect math) instead of
                    # placing flattened text that lost the fraction/super/subscript layout.
                    try:
                        pix = src[b.page].get_pixmap(clip=r, dpi=200)
                        page.insert_image(r, pixmap=pix)
                        continue
                    except Exception:
                        pass   # fall through to text placement if the crop fails
                if b.type == BlockType.TABLE and b.table:
                    try:
                        page.insert_htmlbox(r, _table_html(b.table.rows), scale_low=0)
                    except Exception:
                        pass
                    continue
                if not b.output_text.strip():
                    continue
                if _is_mixed_bidi(b.output_text):
                    b.flags["bidi_mixed"] = (
                        "mixed RTL+LTR on one line — verify word order")
                htmlbox, size = _block_html(b)
                grown = _grow_rect(r, obstacles, h)
                try:
                    ret = page.insert_htmlbox(grown, htmlbox, scale_low=0)
                    scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
                    eff = (size or 11) * (scale or 1.0)
                    if eff < LEGIBLE_MIN_PT:
                        b.flags["illegible"] = (
                            f"rendered at {eff:.1f}pt (< {LEGIBLE_MIN_PT:.0f}pt) — box too tight")
                except Exception:
                    page.insert_textbox(r, b.output_text, fontsize=size, align=0)
        _subset_pages(out, cfg)
        _apply_pdf_metadata(out, doc)
        out.save(out_path, garbage=4, deflate=True)
    finally:
        out.close()
        if src is not None:
            src.close()
    return out_path
