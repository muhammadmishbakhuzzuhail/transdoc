"""PDF extraction via PyMuPDF.

Digital PDFs: pull text blocks with bbox + font/size so we can infer headings and keep
layout. Scanned / mixed PDFs: rasterize the image-only pages and hand them to OCR.
"""

from __future__ import annotations

import re
import unicodedata

from ..config import Config, Fidelity
from ..ir import BBox, Block, BlockType, Cell, Confidence, Document, Run, Style, Table, TocEntry
from .base import block_id, column_reading_order
from .spacing import merge_if_only_spacing, text_in_bbox

# Some PDFs embed CID fonts with no ToUnicode CMap: get_text() then returns the raw glyph
# ids — control chars / mojibake, not real text. Valid pages (any script) have ~0% control
# chars; the broken pages measured 34-49%. Above this fraction we don't trust the digital
# text and rasterize the page for OCR instead.
_GARBAGE_CTRL = 0.10
_BAD_CATS = {"Cc", "Cf", "Co", "Cs", "Cn"}


def _looks_garbage(text: str) -> bool:
    s = text.strip()
    if len(s) < 20:
        return False
    # Subsetted/CID fonts without a ToUnicode CMap make extraction emit "GLYPH<c=...>"
    # placeholders or the U+FFFD replacement char — a strong "needs OCR" signal. (research)
    if "GLYPH<" in s:
        return True
    bad = sum(1 for c in s
              if (c not in "\t\n\r" and unicodedata.category(c) in _BAD_CATS) or c == "�")
    return bad / len(s) > _GARBAGE_CTRL


# A page with thousands of vector paths but almost no extractable text is text-rendered-as-
# outlines (glyphs drawn as geometry, no font) -> OCR. Forms have hundreds of rules but plenty
# of text, so the high path count + near-empty text together avoid false positives. (research)
_GEOMETRY_PATHS = 2000
_GEOMETRY_MAX_TEXT = 100


def _text_as_geometry(page) -> bool:
    try:
        if len(page.get_text("text").strip()) >= _GEOMETRY_MAX_TEXT:
            return False
        return len(page.get_drawings()) >= _GEOMETRY_PATHS
    except Exception:
        return False


def _parse_pages(spec: str | None, total: int) -> set[int] | None:
    """Parse a 1-based page selection ("3-7,10,15-") to a 0-based index set. None -> all."""
    if not spec or not spec.strip():
        return None
    sel: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            if "-" in part:
                a, _, b = part.partition("-")
                start = int(a) if a.strip() else 1
                end = int(b) if b.strip() else total
            else:
                start = end = int(part)
        except ValueError:
            continue   # malformed part (e.g. "a-5") -> skip it, don't crash the pipeline
        for p in range(start, end + 1):
            if 1 <= p <= total:
                sel.add(p - 1)
    return sel or None


# A word hyphenated across a line break ("inter-\nnational") extracts as "inter- national"
# once lines are space-joined. Re-stitch it: lowercase letter + "-" + spaces + lowercase
# letter -> one word. Real compounds ("well-known") have no space after the hyphen, so they
# are left intact.
_HYPHEN_BREAK = re.compile(r"([a-zà-öø-ÿ])-\s+([a-zà-öø-ÿ])")


def _dehyphenate(text: str) -> str:
    return _HYPHEN_BREAK.sub(r"\1\2", text)


# Math operators/relations that signal a formula line (not just an inline "h = 8").
_MATH_OPS = set("=<>≤≥≠≈∈∉⊂⊆∪∩∑∏∫√∂∇∞∼≅≡↦→⊕⊗±×÷·")


def _looks_formula(text: str) -> bool:
    """Heuristic: a short line with a math operator, few real words, and several lone
    variable letters is an equation — mark it FORMULA so it is preserved verbatim instead
    of being translated (which turns `head_i = Attention(...)` into `head; = Perhatian(...)`
    and scrambles sub/superscripts). Tuned to skip prose with an inline `h = 8`."""
    s = text.strip()
    if not s or len(s) > 200 or not any(c in _MATH_OPS for c in s):
        return False
    words = re.findall(r"[A-Za-z]{4,}", s)            # multi-letter tokens = prose words
    singles = re.findall(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])", s)  # lone variable letters
    return len(words) <= 6 and len(singles) >= 3


def _looks_tabular(text: str) -> bool:
    """A block dominated by numeric tokens is a table's data row(s) that the PDF parser
    merged into one block (PyMuPDF doesn't reconstruct cells). Translating it reflows the
    numbers into running text and destroys the grid, so preserve it verbatim. Tuned to skip
    prose that merely mentions a few numbers."""
    toks = text.split()
    if len(toks) < 8:
        return False
    # A token counts as numeric only if it actually contains a digit. Without the digit
    # guard, the dotted leaders in form line-items (". . . . . .") match [\d.,]+ and inflate
    # the count, so IRS-style label rows get frozen verbatim and never translated.
    nums = sum(1 for t in toks if re.fullmatch(r"[\d.,]+%?", t) and any(c.isdigit() for c in t))
    return nums >= 6 and nums / len(toks) > 0.35


_NUMBERED_HEADING = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")

# Bullet (•, -, *, –, …) or "N." / "N)" at line start = a list item. Numbered headings
# ("1 Overview", no period) are not matched and fall through to heading detection.
_LIST_MARKER = re.compile(r"^\s*(?:[•◦▪‣·*\-–—]|\d{1,2}[.)])\s+")


def _alignment(x0: float, x1: float, page_width: float,
               text: str = "", btype: "BlockType | None" = None) -> str | None:
    """Infer paragraph alignment from where the block sits across the page. Full-width body
    text -> None (left); a narrow block with big equal margins -> center; flush-right -> right.
    Returned in Style.align and applied by the reflow renderer.

    Only headings/titles/captions and short runs are eligible: a long body paragraph that
    merely happens to sit in an indented column (e.g. a form field) must not be centred or
    right-aligned just because of its position — that mangled reflowed forms."""
    if page_width <= 0:
        return None
    eligible = btype in (BlockType.TITLE, BlockType.HEADING, BlockType.CAPTION) \
        or len(text) <= 60
    if not eligible:
        return None
    left, right = x0, page_width - x1
    if (x1 - x0) > page_width * 0.8:          # spans most of the width -> ordinary left/justify
        return None
    if abs(left - right) < page_width * 0.06 and left > page_width * 0.12:
        return "center"
    if right < page_width * 0.08 and left > page_width * 0.25:
        return "right"
    return None


def _span_style(span) -> Style:
    flags = span.get("flags", 0)
    c = span.get("color")
    return Style(bold=bool(flags & 16), italic=bool(flags & 2),
                 superscript=bool(flags & 1), size=round(span.get("size", 0.0), 1),
                 color=f"#{c & 0xFFFFFF:06x}" if isinstance(c, int) else None,
                 font=("monospace" if flags & 8 else "serif" if flags & 4 else "sans-serif"))


def _line_spacing(lines, size: float) -> float | None:
    """Estimate line-height (multiple of font size) from the baseline gaps between a block's
    lines. PDF has no line-spacing attribute, so derive it geometrically: median(baseline_gap) /
    font_size. Returns None when there's only one line or the value is out of a sane range."""
    import statistics
    ys = []
    for ln in lines:
        spans = ln.get("spans") or []
        if spans and "origin" in spans[0]:
            ys.append(float(spans[0]["origin"][1]))
        elif ln.get("bbox"):
            ys.append(float(ln["bbox"][1]))
    ys.sort()
    gaps = [b - a for a, b in zip(ys, ys[1:]) if b - a > 0.1]
    if not gaps or not size or size <= 0:
        return None
    mult = statistics.median(gaps) / size
    return round(mult, 2) if 0.9 <= mult <= 3.0 else None


def _runs_from_spans(lines) -> list[Run]:
    """Group a block's spans into inline runs by style (merging adjacent same-style). Returns []
    for a uniformly-styled block so the block-level path is used unchanged."""
    def key(s: Style):
        return (s.bold, s.italic, s.underline, s.superscript, s.size, s.color, s.font)

    runs: list[Run] = []
    for line in lines:
        for span in line.get("spans", []):
            txt = span.get("text", "")
            if not txt:
                continue
            st = _span_style(span)
            if runs and key(runs[-1].style) == key(st):
                runs[-1].text += txt
            else:
                runs.append(Run(text=txt, style=st))
        if runs:
            runs[-1].text += " "
    if len({key(r.style) for r in runs}) <= 1:
        return []
    return runs


def _guess_type(size: float, body_size: float, bold: bool = False,
                text: str = "") -> BlockType:
    """Larger-than-body font -> heading/title. Also catch same-size headings the font ratio
    misses: a short bold line with no terminal punctuation ("Abstract"), or a section-numbered
    line ("3.1 Model Architecture")."""
    if size >= body_size * 1.6:
        return BlockType.TITLE
    if size >= body_size * 1.2:
        return BlockType.HEADING
    t = text.strip()
    if t and len(t) <= 70:
        if _NUMBERED_HEADING.match(t):
            return BlockType.HEADING
        # bold same-size heading: short, no terminal punctuation, and not an author/affiliation
        # byline (those are bold too but carry an email and several name tokens).
        no_terminal = not t.endswith((".", ":", ";", ",", "!", "?"))
        if bold and no_terminal and "@" not in t and len(t.split()) <= 8:
            return BlockType.HEADING
    return BlockType.PARAGRAPH


def _body_size(page) -> float:
    sizes: dict[float, int] = {}
    d = page.get_text("dict")
    for blk in d.get("blocks", []):
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                s = round(span["size"], 1)
                sizes[s] = sizes.get(s, 0) + len(span.get("text", ""))
    if not sizes:
        return 11.0
    return max(sizes, key=sizes.get)  # most common size by char count = body text


def extract(path: str, cfg: Config, ocr_pages: set[int] | None = None) -> Document:
    """Extract a PDF. ``ocr_pages`` (0-based) are rasterized and OCR'd instead of parsed."""
    import fitz

    from ..ocr import get_ocr

    import tempfile
    from pathlib import Path

    ocr_pages = ocr_pages or set()
    try:
        doc = fitz.open(path)
    except Exception as e:
        raise ValueError(f"unreadable or corrupt PDF: {e}") from e
    out = Document(source_path=path, mime="application/pdf", page_count=doc.page_count)
    out.metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
    try:
        out.toc = [TocEntry(level=int(lv), title=str(ti), page=int(pg))
                   for lv, ti, pg in (doc.get_toc() or [])]
    except Exception:
        pass

    # Real cell-level table recovery (PyMuPDF find_tables) is only used for FLOW output
    # (->DOCX/MD/flow-PDF), where the renderer builds a grid from Table/Cell IR. The LAYOUT
    # overlay keeps the per-text-block path (each cell is already a positioned block, and the
    # grid lines are preserved by the line-art-keeping redaction), so we don't reshape it.
    flow_target = cfg.resolve_fidelity(source_is_pdf=True) == Fidelity.FLOW

    selected = _parse_pages(getattr(cfg, "pages", None), doc.page_count)
    ocr = get_ocr(cfg) if ocr_pages else None
    img_dir = Path(tempfile.mkdtemp(prefix="transdoc_img_"))
    out.tmp_dirs.append(str(img_dir))

    def _ensure_ocr():
        nonlocal ocr
        if ocr is None:
            ocr = get_ocr(cfg)
        return ocr

    def _ocr_page(page, pno) -> None:
        eng = _ensure_ocr()
        pix = page.get_pixmap(dpi=300)
        out.blocks.extend(eng.recognize_image_bytes(pix.tobytes("png"), cfg, page=pno))

    _PT_TO_300 = 300.0 / 72.0

    def _ocr_figure(page, bb, pno) -> None:
        """OCR a large embedded image (a scan dropped onto a digital page) and emit its text
        as translatable OCR blocks, with bboxes mapped to the page in the 300-dpi-pixel space
        the overlay expects (so `_block_rect` scales them back to points correctly)."""
        page_area = abs(page.rect.width * page.rect.height) or 1.0
        if abs((bb.x1 - bb.x0) * (bb.y1 - bb.y0)) / page_area < 0.08:
            return  # too small (icon/logo/chart marker) to be worth OCRing
        eng = _ensure_ocr()
        pm = page.get_pixmap(clip=bb, dpi=300)
        for ob in eng.recognize_image_bytes(pm.tobytes("png"), cfg, page=pno):
            if ob.bbox:
                ox, oy = bb.x0 * _PT_TO_300, bb.y0 * _PT_TO_300
                ob.bbox = BBox(x0=ob.bbox.x0 + ox, y0=ob.bbox.y0 + oy,
                               x1=ob.bbox.x1 + ox, y1=ob.bbox.y1 + oy)
            out.blocks.append(ob)

    from .annots import capture as _capture_annots
    from .vectors import capture as _capture_vectors
    from .vectors import page_background as _page_bg

    for pno, page in enumerate(doc):
        out.page_sizes[pno] = (page.rect.width, page.rect.height)
        out.page_drawings[pno] = _capture_vectors(page)
        ann = _capture_annots(page)
        if ann:
            out.page_annots[pno] = ann
        bg = _page_bg(page)
        if bg:
            out.page_background[pno] = bg
        rot = int(getattr(page, "rotation", 0) or 0)
        if rot:
            out.page_rotation[pno] = rot

        if selected is not None and pno not in selected:
            continue  # page not in the requested selection — skip extraction/translation

        if pno in ocr_pages:
            try:
                _ocr_page(page, pno)
            except Exception:
                pass  # one page's OCR failing must not sink the whole document
            continue

        # Trust digital text only if it isn't CID-font garbage or text-rendered-as-outlines;
        # otherwise OCR the page.
        if _looks_garbage(page.get_text()) or _text_as_geometry(page):
            try:
                _ocr_page(page, pno)
                continue
            except Exception:
                pass  # OCR unavailable -> fall through and keep whatever text we have

        # extract embedded images as FIGURE blocks (so flow output can reinsert them)
        for ii, info in enumerate(page.get_images(full=True)):
            xref = info[0]
            try:
                rects = page.get_image_rects(xref)
                bb = rects[0] if rects else None
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:  # CMYK -> RGB
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fpath = img_dir / f"p{pno}_img{ii}.png"
                pix.save(str(fpath))
                out.blocks.append(Block(
                    id=f"p{pno}-fig{ii}", type=BlockType.FIGURE, page=pno,
                    image_path=str(fpath),
                    bbox=BBox(x0=bb.x0, y0=bb.y0, x1=bb.x1, y1=bb.y1) if bb else None,
                    confidence=Confidence(source="digital")))
                if cfg.ocr_figures and bb is not None:
                    try:
                        _ocr_figure(page, bb, pno)
                    except Exception:
                        pass  # OCR unavailable / failed on this image -> keep the figure only
            except Exception:
                continue

        # Recover real tables (FLOW only) as Table/Cell IR; remember their regions so the
        # same text isn't also emitted as loose paragraphs below.
        table_rects: list = []
        # find_tables is ~130 ms/page; a page with zero vector graphics can't hold a ruled
        # table, so skip it there (cheap get_drawings gate) without losing any real tables.
        if flow_target and page.get_drawings():
            try:
                for ti, tbl in enumerate(page.find_tables().tables):
                    grid = [[Cell(text=(c or "").strip()) for c in row]
                            for row in tbl.extract()]
                    ncols = max((len(r) for r in grid), default=0)
                    ncells = sum(len(r) for r in grid) or 1
                    filled = sum(1 for r in grid for c in r if c.text)
                    # real grid: >=2x2 AND mostly-populated cells (a diagram detected as a
                    # table is typically sparse), so figures don't get mangled into tables.
                    if len(grid) >= 2 and ncols >= 2 and filled / ncells >= 0.5:
                        tb = tbl.bbox
                        out.blocks.append(Block(
                            id=f"p{pno}-tbl{ti}", type=BlockType.TABLE, page=pno,
                            table=Table(rows=grid),
                            bbox=BBox(x0=tb[0], y0=tb[1], x1=tb[2], y1=tb[3]),
                            confidence=Confidence(source="digital")))
                        table_rects.append(fitz.Rect(tb))
            except Exception:
                pass

        body = _body_size(page)
        d = page.get_text("dict")
        raw_blocks = None         # lazily filled with get_text("rawdict") only if a suspect block appears
        idx = 0
        for blk in d.get("blocks", []):
            lines = blk.get("lines", [])
            if not lines:
                continue
            text_parts: list[str] = []
            max_size = 0.0
            # The overlay applies one style to the whole (reflowed) block, so derive bold/
            # italic from the CHARACTER MAJORITY — a heading (all bold) stays bold, but a
            # paragraph with one bold word does not turn the whole block bold. Font + colour
            # come from the dominant (largest) span.
            bold_chars = ital_chars = total_chars = 0
            dom_size = -1.0
            dom_flags = 0
            color: str | None = None
            for line in lines:
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    text_parts.append(txt)
                    sz = span.get("size", 0)
                    max_size = max(max_size, sz)
                    flags = span.get("flags", 0)
                    nchar = len(txt.strip())
                    total_chars += nchar
                    if flags & 2 ** 4:   # bold
                        bold_chars += nchar
                    if flags & 2 ** 1:   # italic
                        ital_chars += nchar
                    if sz > dom_size and txt.strip():
                        dom_size = sz
                        dom_flags = flags
                        c = span.get("color")
                        if isinstance(c, int):
                            color = f"#{c & 0xFFFFFF:06x}"
                text_parts.append(" ")
            bold = total_chars > 0 and bold_chars > total_chars * 0.5
            italic = total_chars > 0 and ital_chars > total_chars * 0.5
            # Map the source font to a CSS generic family so a thin serif (e.g. Computer
            # Modern) renders serif, not a heavier sans default — the actual face isn't
            # embeddable here. flags: bit2 = serif, bit3 = monospace.
            font = ("monospace" if dom_flags & 2 ** 3 else
                    "serif" if dom_flags & 2 ** 2 else "sans-serif")
            text = _dehyphenate("".join(text_parts).strip())
            if not text:
                continue
            # Glyph-gap word spacing (research item F): a very long run with no space hints at
            # missing space glyphs; re-derive spacing from rawdict geometry, adopt only if it
            # differs purely by added spaces. Cheap because it only fires on the rare suspect.
            if max((len(w) for w in text.split()), default=0) >= 25:
                if raw_blocks is None:
                    raw_blocks = page.get_text("rawdict").get("blocks", [])
                spaced = _dehyphenate(text_in_bbox(raw_blocks, blk["bbox"]).strip())
                text = merge_if_only_spacing(text, spaced)
            x0, y0, x1, y1 = blk["bbox"]
            if table_rects:
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                if any(r.contains(fitz.Point(cx, cy)) for r in table_rects):
                    continue  # this text is already captured as a table cell
            # Tall, very narrow blocks are rotated/vertical sidebar text (e.g. an arXiv ID);
            # never promote them to a heading/title — they pollute reflowed output.
            w, h = x1 - x0, y1 - y0
            vertical = w < 40 and h > w * 4
            if _looks_formula(text):
                btype = BlockType.FORMULA
            elif _looks_tabular(text):
                btype = BlockType.TABLE  # merged numeric table rows -> preserve verbatim
            elif vertical:
                btype = BlockType.CAPTION
            elif _LIST_MARKER.match(text):
                btype = BlockType.LIST_ITEM
                # strip the bullet/number marker — the reflow's <li> adds its own
                text = _LIST_MARKER.sub("", text, count=1)
            else:
                btype = _guess_type(max_size, body, bold, text)
            align = _alignment(x0, x1, page.rect.width, text=text, btype=btype)
            # inline runs only for flowing prose (not formula/table/list-marker blocks)
            runs = (_runs_from_spans(lines)
                    if btype in (BlockType.PARAGRAPH, BlockType.CAPTION) else [])
            out.blocks.append(
                Block(
                    id=block_id(pno, idx),
                    type=btype,
                    page=pno,
                    text=text,
                    bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    style=Style(size=max_size, bold=bold, italic=italic, font=font,
                                color=color, align=align,
                                line_spacing=_line_spacing(lines, max_size),
                                heading_level=1 if btype == BlockType.HEADING else 0),
                    runs=runs,
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1

    if getattr(cfg, "layout", "off") != "off":
        try:
            _apply_layout(doc, out, cfg)
        except Exception:
            pass   # layout model unavailable -> keep the heuristic blocks

    from .links import attach_pdf_links
    for pno in range(doc.page_count):
        attach_pdf_links(doc[pno], [b for b in out.blocks if b.page == pno])

    doc.close()
    from .block_types import detect_running_heads
    detect_running_heads(out)   # running header/footer + page-number typing (margin + repetition)
    column_reading_order(out)   # multi-column-aware reading order (research)
    from .base import associate_captions
    associate_captions(out)     # keep each caption adjacent to its figure/table
    return out


def _apply_layout(fdoc, out: Document, cfg: Config) -> None:
    """Use a layout-detection model to replace per-block heuristics: text inside a non-text
    region (figure/formula/chart/table) is dropped and the whole region is added as a
    crop_region block so the renderer crops it verbatim from the source (pixel-perfect math/
    diagrams). Text regions keep their reflowable blocks. Only digital (point-bbox) pages."""
    from ..layout import NON_TEXT_LABELS, get_detector

    det = get_detector(cfg.layout)
    by_page: dict[int, list] = {}
    for b in out.blocks:
        by_page.setdefault(b.page, []).append(b)

    # Pages we extracted that aren't OCR (OCR bboxes are 300-dpi pixels, not points). Detect
    # them all in one shot — the subprocess detector imports paddle once for the whole batch.
    detect_pnos = [pno for pno in sorted(by_page)
                   if not any(b.confidence.source == "ocr" for b in by_page[pno])]
    if hasattr(det, "detect_pages"):
        regions_by_page = det.detect_pages(fdoc, detect_pnos)
    else:
        regions_by_page = {pno: det.detect(fdoc[pno]) for pno in detect_pnos}

    kept: list[Block] = []
    ridx = 0
    for pno in sorted(by_page):          # only pages we actually extracted (respects --pages)
        page_blocks = by_page[pno]
        if pno not in regions_by_page:   # OCR page -> untouched
            kept.extend(page_blocks)
            continue
        nontext = [r for r in regions_by_page[pno] if r.label in NON_TEXT_LABELS]
        # Only DISPLAY (block-level) formulas are cropped. Inline math ($d_k$, $\sqrt{d_k}$
        # inside a prose line) is left as flowing text: its crop is tiny and would be painted
        # ON TOP of the reflowed translation, covering the surrounding words. Subscripts are
        # lost (flattened text), but the prose stays clean and nothing is overwritten.
        crop = [r for r in nontext if _crop_worthy(r)]
        if not crop:
            kept.extend(page_blocks)
            continue

        for b in page_blocks:
            # Drop a block only if it actually sits under a cropped region — including figures
            # (a heuristic/OCR figure covered by a layout crop is superseded). A figure NOT
            # covered by any crop (a standalone embedded image the layout model missed) is kept,
            # not silently lost.
            if b.bbox and any(_covers(b.bbox, r, b.text) for r in crop):
                continue
            kept.append(b)
        for r in crop:
            kept.append(Block(
                id=f"p{pno}-crop{ridx}", type=BlockType.FIGURE, page=pno, crop_region=True,
                bbox=BBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1),
                confidence=Confidence(source="digital")))
            ridx += 1
    out.blocks = kept


# Inline formulas are small; anything below this (in points) is treated as inline text, not
# cropped. Display equations and figures/tables/charts are well above it.
_INLINE_MAX_W = 50.0
_INLINE_MAX_H = 20.0


def _crop_worthy(r) -> bool:
    """A detected non-text region big enough to crop verbatim. Tiny formula regions are
    inline math and must stay as text (see _apply_layout)."""
    if r.label in ("formula", "formula_number"):
        return (r.x1 - r.x0) >= _INLINE_MAX_W or (r.y1 - r.y0) >= _INLINE_MAX_H
    return True


def _covers(bbox, r, text: str = "", frac: float = 0.5) -> bool:
    """True if the block bbox belongs to cropped region r and should be dropped:
      - its center is inside r, or
      - r covers >= ``frac`` (0.5) of the block's area, or
      - the block is a SHORT fragment (< 40 chars) overlapping r by > 0.1.
    The last case catches an equation's ragged tail (e.g. ``√dk )V (1)``) that the detector's
    formula box under-covers — these get painted over the crop. A long prose paragraph that
    merely grazes a region edge needs the full 0.5 and is protected."""
    cx, cy = (bbox.x0 + bbox.x1) / 2, (bbox.y0 + bbox.y1) / 2
    if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
        return True
    ix = max(0.0, min(bbox.x1, r.x1) - max(bbox.x0, r.x0))
    iy = max(0.0, min(bbox.y1, r.y1) - max(bbox.y0, r.y0))
    area = max((bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0), 1e-6)
    ov = (ix * iy) / area
    return ov >= frac or (ov > 0.1 and len(text.strip()) < 40)
