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

# Direction detection + raw-draw shaping live in textdir (single source of truth).
from ..textdir import is_mixed_bidi as _is_mixed_bidi  # noqa: E402
from ..textdir import shape_for_raw_draw  # noqa: E402


def _esc(s: str) -> str:
    return html.escape(s)


def _apply_pdf_toc(pdf, doc) -> None:
    """Rebuild the PDF outline/bookmarks with translated titles (clamped to page count)."""
    if not getattr(doc, "toc", None):
        return
    n = pdf.page_count
    toc = [[max(1, e.level), e.output_text, min(max(1, e.page), n)]
           for e in doc.toc if e.output_text.strip()]
    if toc:
        try:
            pdf.set_toc(toc)
        except Exception:
            pass


def _apply_pdf_metadata(pdf, doc) -> None:
    """Carry the source document metadata (title/author/subject/keywords/creator) onto the
    output PDF — captured in extract but previously not written out."""
    md = getattr(doc, "metadata", None)
    keep = {k: md[k] for k in ("title", "author", "subject", "keywords", "creator")
            if md and md.get(k)}
    if keep:
        try:
            pdf.set_metadata(keep)
        except Exception:
            pass
    # Tag the output's document language as the TARGET (catalog /Lang) so readers/AT announce
    # the translated text in the right language. (DOCX gets the same via _set_doc_language.)
    lang = getattr(doc, "target_lang", None)
    if lang:
        try:
            pdf.xref_set_key(pdf.pdf_catalog(), "Lang", f"({str(lang).replace('_', '-')})")
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
                # underline + strikethrough share the text-decoration property
                _deco = ([("underline")] if b.style.underline else []) + \
                        (["line-through"] if b.style.strike else [])
                ul_css = f"text-decoration:{' '.join(_deco)};" if _deco else ""
                color_css = f"color:{b.style.color};" if b.style.color else ""
                # small-caps / all-caps / highlight (block-level char styles the overlay dropped)
                extra_css = ("".join(c + ";" for c in _char_css(b.style)))
                _inner = _runs_html(b.runs) if b.runs else _esc(b.output_text)
                if b.style.link and not b.runs:
                    _inner = f'<a href="{_esc(b.style.link)}">{_inner}</a>'
                htmlbox = (f'<div style="{dir_css}{weight_css}{italic_css}{ul_css}{color_css}'
                           f'{extra_css}font-size:{size:.0f}px;text-align:{align};'
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
                    # raw glyph draw — no HarfBuzz/UBA here, so reshape+reorder RTL ourselves
                    raw = shape_for_raw_draw(b.output_text, rtl)
                    page.insert_textbox(r, raw, fontsize=size, align=2 if rtl else 0)

        # If only some pages were selected (--pages), the overlay covered just those; the rest
        # are still untranslated original. Drop them so the output isn't a translated/source mix.
        _subset_pages(pdf, cfg)
        _apply_pdf_metadata(pdf, doc)
        _apply_pdf_toc(pdf, doc)
        _save_pdf(pdf, out_path)
    finally:
        pdf.close()
    return out_path


def _save_pdf(pdf, out_path: str) -> None:
    """Subset embedded fonts (keep only used glyphs) before saving — a full CJK/Indic fallback
    face is multi-MB; subsetting shrinks the output a lot. Best-effort; plain save on failure."""
    try:
        pdf.subset_fonts()
    except Exception:
        pass
    pdf.save(out_path, garbage=4, deflate=True)


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
                raw = shape_for_raw_draw(b.output_text, rtl)
                page.insert_textbox(r, raw, fontsize=11, align=2 if rtl else 0)

        # Output a translated image when the target is an image (the natural Lens-style
        # result: upload a photo, get the photo back translated), else an image-backed PDF.
        ext = out_path.lower().rsplit(".", 1)[-1]
        if ext in ("png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"):
            page.get_pixmap().save(out_path)   # identity matrix -> original pixel dimensions
        else:
            _save_pdf(pdf, out_path)
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
        _save_pdf(pdf, out_path)
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
            parts.append(_table_html(b.table))
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


def _cell_td(c, pad=None) -> str:
    """One <td> honoring the cell's font size, weight, alignment and row/col span (was a fixed
    8pt with spans ignored)."""
    style = ["border:1px solid #000",
             f"padding:{pad:.0f}pt" if pad and pad > 0 else "padding:2px",
             f"font-size:{c.size:.0f}pt" if c.size and c.size > 0 else "font-size:8pt"]
    if c.bold:
        style.append("font-weight:bold")
    if c.align in ("center", "right"):
        style.append(f"text-align:{c.align}")
    if c.shading:
        style.append(f"background-color:{c.shading}")
    span = ""
    if c.colspan > 1:
        span += f' colspan="{c.colspan}"'
    if c.rowspan > 1:
        span += f' rowspan="{c.rowspan}"'
    inner = _table_html(c.table) if c.table else _esc(c.output_text)
    return f'<td style="{";".join(style)}"{span}>{inner}</td>'


def _table_html(table) -> str:
    """Accepts an IR Table (uses rows + col_widths + row_heights + cell_margin) or a bare list
    of rows."""
    rows = getattr(table, "rows", table)
    widths = getattr(table, "col_widths", None) or []
    heights = getattr(table, "row_heights", None) or []
    pad = getattr(table, "cell_margin", None)
    colgroup = ""
    if widths:
        colgroup = "<colgroup>" + "".join(
            f'<col style="width:{w:.0f}pt">' if w and w > 0 else "<col>"
            for w in widths) + "</colgroup>"
    parts = []
    for i, row in enumerate(rows):
        h = heights[i] if i < len(heights) else 0
        tr_style = f' style="height:{h:.0f}pt"' if h and h > 0 else ""
        parts.append(f"<tr{tr_style}>" + "".join(_cell_td(c, pad) for c in row) + "</tr>")
    body = "".join(parts)
    return (f'<table style="border-collapse:collapse;border:1px solid #000">'
            f'{colgroup}{body}</table>')


def _norm_rect(b):
    """Block bbox -> PDF points. OCR blocks carry 300-dpi pixels (page was rasterised); digital
    blocks are already in points."""
    import fitz
    s = 72.0 / 300.0 if b.confidence.source == "ocr" else 1.0
    bb = b.bbox
    return fitz.Rect(bb.x0 * s, bb.y0 * s, bb.x1 * s, bb.y1 * s)


_HIGHLIGHT_CSS = {
    "yellow": "#ffff00", "bright_green": "#00ff00", "turquoise": "#40e0d0", "pink": "#ffc0cb",
    "blue": "#0000ff", "red": "#ff0000", "dark_blue": "#000080", "teal": "#008080",
    "green": "#008000", "violet": "#ee82ee", "dark_red": "#8b0000", "dark_yellow": "#808000",
    "gray_50": "#808080", "gray_25": "#c0c0c0",
}


def _hl_css(name: str | None) -> str | None:
    if not name:
        return None
    return name if name.startswith("#") else _HIGHLIGHT_CSS.get(name, "#ffff00")


def _char_css(s) -> list[str]:
    """Shared character-decoration CSS for a Style: super/sub, small-caps, highlight."""
    css = []
    if s.small_caps:
        css.append("font-variant:small-caps")
    if s.all_caps:
        css.append("text-transform:uppercase")
    hl = _hl_css(s.highlight)
    if hl:
        css.append(f"background-color:{hl}")
    return css


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
    css += _char_css(s)
    inner = _esc(run.output_text)
    if s.link:
        inner = f'<a href="{_esc(s.link)}">{inner}</a>'
    return f'<span style="{";".join(css)}">{inner}</span>' if css else inner


def _runs_html(runs) -> str:
    return "".join(_run_span(r) for r in runs)


def _block_html(b, compress: bool = False):
    """Styled HTML for a block (size/bold/italic/colour/align/rtl) -> (html, size_pt).

    ``compress`` is Area-C tier 1: when the translation is longer than the source, tighten leading
    to ~1.0 and drop paragraph spacing so the text reclaims vertical space BEFORE any font shrink or
    cascade — the cheapest way to absorb expansion without moving the block."""
    size = b.style.size or 11
    rtl = b.style.rtl
    is_heading = b.type in (BlockType.TITLE, BlockType.HEADING)
    if b.style.align in ("center", "right", "justify"):
        align = b.style.align
    elif not is_heading and len(b.output_text) > 40:
        align = "right" if rtl else "justify"
    else:
        align = "right" if rtl else "left"
    css = [f"font-size:{size:.1f}pt", f"text-align:{align}",
           f"line-height:{'1.0' if compress else '1.05'}"]
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
    css += _char_css(b.style)
    if b.style.space_before and not compress:
        css.append(f"margin-top:{b.style.space_before:.0f}pt")
    if b.style.space_after and not compress:
        css.append(f"margin-bottom:{b.style.space_after:.0f}pt")
    if b.style.indent_left:
        css.append(f"margin-left:{b.style.indent_left:.0f}pt")
    if b.style.indent_first:
        css.append(f"text-indent:{b.style.indent_first:.0f}pt")
    if b.style.line_spacing and b.style.line_spacing > 0 and not compress:
        css = [c for c in css if not c.startswith("line-height")]
        css.append(f"line-height:{b.style.line_spacing:.2f}")
    if b.style.para_shading:                      # boxed/callout paragraph background
        css.append(f"background-color:{b.style.para_shading}")
    if b.style.para_border:
        css.append("border:1px solid #000")
    if b.style.para_shading or b.style.para_border:
        css.append("padding:3pt")
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


def _redraw_annots(page, annots) -> None:
    """Repaint captured text-markup annotations on top of the placed text: highlights as a
    semi-transparent fill, underline below the span, strikeout through its middle. Overlay keeps
    the source annotations natively; this is only for the reconstruct path."""
    import fitz

    for a in annots or []:
        try:
            color = _hex_rgb(a.get("color")) or (1, 1, 0)
            for (x0, y0, x1, y1) in a.get("quads", []):
                if a["kind"] == "highlight":
                    page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=None, fill=color,
                                   fill_opacity=0.35)
                elif a["kind"] == "underline":
                    page.draw_line(fitz.Point(x0, y1), fitz.Point(x1, y1), color=color, width=1)
                elif a["kind"] == "strikeout":
                    ym = (y0 + y1) / 2
                    page.draw_line(fitz.Point(x0, ym), fitz.Point(x1, ym), color=color, width=1)
        except Exception:
            continue


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
                _kw = {"dashes": d["dashes"]} if d.get("dashes") else {}
                page.draw_line(fitz.Point(d["x0"], d["y0"]), fitz.Point(d["x1"], d["y1"]),
                               color=_hex_rgb(d.get("color")) or (0, 0, 0), width=w, **_kw)
            elif d.get("kind") == "rect":
                _kw = {"dashes": d["dashes"]} if d.get("dashes") else {}
                page.draw_rect(fitz.Rect(d["x0"], d["y0"], d["x1"], d["y1"]),
                               color=_hex_rgb(d.get("color")), fill=_hex_rgb(d.get("fill")),
                               width=w, **_kw)
        except Exception:
            continue


# --- Area C: text-expansion reflow ------------------------------------------------------------
# When a translation runs longer than the source (DE/FI/RU expand ~30%), the original bbox is too
# small. Tiered response, cheapest first: (1) COMPRESS leading; (2) GROW into the whitespace below
# the block; (3) CASCADE — push the following same-column blocks down; (4) SPILL the overflow onto
# a fresh page (the DeepL reflow, page count may grow). Font-shrink + 'illegible' flag stay as the
# final safety net. Strict-fit blocks (no expansion, not pushed) render verbatim at their original
# bbox, so an unexpanded doc (e.g. echo engine) is byte-for-byte the old fixed-layout output.

_PAGE_MARGIN = 36.0       # spill-page top/bottom margin (0.5in)
_BLOCK_GAP = 2.0          # vertical gap kept between cascaded blocks


def _measure_html_height(html: str, width: float) -> float:
    """Height (pt) the HTML needs at the given column width — fitz.Story laid out into a very tall
    column. Approximate (Story's default metrics differ slightly from insert_htmlbox), but enough
    to decide grow/cascade/spill; insert_htmlbox still shrink-fits as the safety net."""
    import fitz

    if width <= 1:
        return 0.0
    try:
        story = fitz.Story(html=html)
        _, filled = story.place(fitz.Rect(0, 0, width, 1_000_000))
        return float(filled[3] - filled[1])
    except Exception:
        return 0.0


def _columns(items: list[dict]) -> list[list[dict]]:
    """Cluster page items into columns by horizontal overlap (newspaper/two-column aware), each
    column sorted top-to-bottom in reading order. Single-column docs collapse to one list."""
    cols: list[dict] = []
    for it in sorted(items, key=lambda x: x["rect"].x0):
        r = it["rect"]
        for c in cols:
            ov = min(c["x1"], r.x1) - max(c["x0"], r.x0)
            if ov > 0.4 * min(c["x1"] - c["x0"], r.x1 - r.x0):
                c["items"].append(it)
                c["x0"], c["x1"] = min(c["x0"], r.x0), max(c["x1"], r.x1)
                break
        else:
            cols.append({"x0": r.x0, "x1": r.x1, "items": [it]})
    for c in cols:
        c["items"].sort(key=lambda x: (x["block"].reading_order, x["rect"].y0))
    return [c["items"] for c in cols]


def _reflow(items: list[dict], page_h: float, anchored: bool) -> tuple[dict, list[dict]]:
    """Assign each item a (top, bottom) on this page; return (placements, overflow).

    anchored=True (a source page): a block that neither expanded nor got pushed keeps its ORIGINAL
    y — identity for unexpanded docs. Expanded/pushed blocks cascade down their column; what no
    longer fits spills. anchored=False (a spill page): stack everything from the top margin."""
    placements: dict[str, tuple[float, float]] = {}
    overflow: list[dict] = []
    usable_bottom = page_h - _PAGE_MARGIN
    fresh_cap = page_h - 2 * _PAGE_MARGIN
    for col in _columns(items):
        # anchored: cursor starts at the page top so the first block keeps its original y; a spill
        # page stacks from the top margin instead.
        cursor = 0.0 if anchored else _PAGE_MARGIN
        spilling = False
        for it in col:
            if spilling:
                overflow.append(it)
                continue
            b, rect, need = it["block"], it["rect"], it["h"]
            expanded = need > rect.height + 1
            if anchored and not expanded and cursor <= rect.y0 + 1:
                # strict fit at the original position — verbatim, no reflow
                top, bottom = rect.y0, rect.y0 + rect.height
                placements[b.id] = (top, bottom)
                cursor = bottom + _BLOCK_GAP
                continue
            top = max(rect.y0, cursor) if anchored else cursor
            h = max(rect.height, need)
            bottom = top + h
            if bottom > usable_bottom and h <= fresh_cap:
                # doesn't fit here but fits a fresh page -> spill this and the rest of the column
                overflow.append(it)
                spilling = True
                continue
            if bottom > usable_bottom:              # taller than a whole page: clamp, shrink-fit
                bottom = usable_bottom
            placements[b.id] = (top, bottom)
            cursor = bottom + _BLOCK_GAP
    overflow.sort(key=lambda x: x["block"].reading_order)
    return placements, overflow


def _block_item(b, page_h: float) -> dict:
    """Pre-measure a text block: pick compressed vs normal styling and the height it needs."""
    r = _norm_rect(b)
    html_n, size = _block_html(b, compress=False)
    need = _measure_html_height(html_n, r.width)
    html, compressed = html_n, False
    if need > r.height + 1:                          # tier 1: try compressed leading
        html_c, _ = _block_html(b, compress=True)
        need_c = _measure_html_height(html_c, r.width)
        if need_c < need:
            html, need, compressed = html_c, need_c, True
    return {"block": b, "rect": r, "h": need, "html": html, "size": size,
            "kind": "text", "compressed": compressed}


def render_reconstruct(doc: Document, cfg: Config, out_path: str) -> str:
    """Positioned per-page reconstruction — the DeepL approach. A fresh page at the SOURCE page
    size for every source page, with each block's translation placed at its ORIGINAL bbox.
    Preserves page count, size, block positions and images for content that fits. When the
    translation expands past its box, the Area-C reflow kicks in (compress -> grow -> cascade ->
    spill to a new page); font-shrink + 'illegible' flag remain the final safety net."""
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
            blocks = [b for b in by_page.get(pno, []) if b.bbox]
            # Pre-measure every block so the reflow knows which ones expanded. Non-text blocks
            # (figure/formula/table) keep their original height in the cascade.
            items: list[dict] = []
            for b in blocks:
                if b.type in (BlockType.FIGURE, BlockType.FORMULA, BlockType.TABLE):
                    items.append({"block": b, "rect": _norm_rect(b),
                                  "h": _norm_rect(b).height, "kind": "media"})
                elif b.output_text.strip():
                    items.append(_block_item(b, h))

            # Lay this source page out, then keep emitting spill pages until everything is placed.
            # The origin page is ALWAYS emitted (even when empty) so an unexpanded doc keeps its
            # 1:1 source-page mapping; spill pages are appended only when content overflows.
            page_items, anchored, origin = items, True, True
            while True:
                placements, overflow = _reflow(page_items, h, anchored) if page_items else ({}, [])
                page = out.new_page(width=w, height=h)
                if origin:                            # backgrounds/vectors/annots use source geom
                    bg = doc.page_background.get(pno)
                    if bg:
                        try:
                            rgb = _hex_rgb(bg)
                            if rgb:
                                page.draw_rect(page.rect, color=rgb, fill=rgb)
                        except Exception:
                            pass
                    _redraw_vectors(page, doc.page_drawings.get(pno, []))
                for it in page_items:
                    pl = placements.get(it["block"].id)
                    if pl is None:                    # spilled to the next page
                        continue
                    _place_item(page, it, pl, src)
                if origin:
                    _redraw_annots(page, doc.page_annots.get(pno, []))
                if not overflow or len(overflow) == len(page_items):
                    break                             # done, or nothing fit (avoid infinite spill)
                page_items, anchored, origin = overflow, False, False
        _subset_pages(out, cfg)
        _apply_pdf_metadata(out, doc)
        _apply_pdf_toc(out, doc)
        _save_pdf(out, out_path)
    finally:
        out.close()
        if src is not None:
            src.close()
    return out_path


def _place_item(page, it: dict, pl: tuple[float, float], src) -> None:
    """Render one reflowed item (media or text) into its assigned rect."""
    import fitz

    b = it["block"]
    orig = it["rect"]
    top, bottom = pl
    r = fitz.Rect(orig.x0, top, orig.x1, bottom)
    if it["kind"] == "media":
        if b.type == BlockType.FIGURE:
            if b.crop_region and src is not None and b.page < src.page_count:
                try:                              # crop the source region at its ORIGINAL geometry
                    page.insert_image(r, pixmap=src[b.page].get_pixmap(clip=orig, dpi=200))
                except Exception:
                    pass
            elif b.image_path:
                try:
                    page.insert_image(r, filename=b.image_path)
                except Exception:
                    pass
            return
        if b.type == BlockType.FORMULA and src is not None and b.page < src.page_count:
            try:
                page.insert_image(r, pixmap=src[b.page].get_pixmap(clip=orig, dpi=200))
                return
            except Exception:
                pass   # fall through to text placement if the crop fails
        if b.type == BlockType.TABLE and b.table:
            try:
                ret = page.insert_htmlbox(r, _table_html(b.table), scale_low=0)
                scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
                if scale and scale < OVERFLOW_FLAG_SCALE:
                    b.flags["text_expansion"] = (
                        f"table shrunk to {scale:.0%} to fit — verify legibility/layout")
            except Exception:
                pass
        return
    # text
    if _is_mixed_bidi(b.output_text):
        b.flags["bidi_mixed"] = "mixed RTL+LTR on one line — verify word order"
    size = it["size"]
    try:
        ret = page.insert_htmlbox(r, it["html"], scale_low=0)
        scale = ret[1] if isinstance(ret, (tuple, list)) and len(ret) > 1 else 1.0
        eff = (size or 11) * (scale or 1.0)
        if eff < LEGIBLE_MIN_PT:
            b.flags["illegible"] = (
                f"rendered at {eff:.1f}pt (< {LEGIBLE_MIN_PT:.0f}pt) — box too tight")
        elif scale and scale < OVERFLOW_FLAG_SCALE:
            b.flags["text_expansion"] = (
                f"shrunk to {scale:.0%} to fit box — verify legibility/layout")
    except Exception:
        raw = shape_for_raw_draw(b.output_text, b.style.rtl)
        page.insert_textbox(r, raw, fontsize=size, align=2 if b.style.rtl else 0)
