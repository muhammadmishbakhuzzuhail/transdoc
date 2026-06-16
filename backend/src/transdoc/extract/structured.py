"""Structured PDF extraction via PP-StructureV3: build the IR straight from detected regions,
keeping **formulas as LaTeX** and figures/tables/seals as verbatim crops. Text regions use the
digital text layer when present (perfect), falling back to the region's OCR content (scans).

Targets PDF -> Markdown/DOCX. Formulas keep LaTeX (display + inline), tables become cells,
figures/seals are verbatim crops. See ppstructurev3-region-router."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from ..config import Config
from ..ir import BBox, Block, BlockType, Cell, Confidence, Document, Style, Table

# PP-FormulaNet spaces every character inside \operatorname{}/\text{} ("A t t e n t i o n",
# "s o f t m a x"). In math mode spaces are ignored, but inside those upright groups they
# render literally — collapse single-letter spacing so it reads "Attention", "softmax".
_LETTER_SP = re.compile(r"(?<=[A-Za-z]) (?=[A-Za-z])")
_INLINE_MATH = re.compile(r"\$[^$\n]{1,200}\$")


def _clean_latex(s: str) -> str:
    prev = None
    while prev != s:           # repeat so "A t t" fully collapses
        prev = s
        s = _LETTER_SP.sub("", s)
    return s

# PP-StructureV3 block_label -> our BlockType.
_LABEL = {
    "doc_title": BlockType.TITLE,
    "title": BlockType.TITLE,
    "paragraph_title": BlockType.HEADING,
    "text": BlockType.PARAGRAPH,
    "abstract": BlockType.PARAGRAPH,
    "footnote": BlockType.PARAGRAPH,
    "reference": BlockType.PARAGRAPH,
    "content": BlockType.PARAGRAPH,
    "figure_title": BlockType.CAPTION,
    "table_title": BlockType.CAPTION,
    "formula": BlockType.FORMULA,
}
# Regions cropped verbatim from the source (no text reflow). Tables are handled separately
# (HTML -> cells); they fall back to a crop only if parsing fails.
_CROP = {"image", "figure", "chart", "seal", "stamp"}


def _cell_align(style: str | None) -> str | None:
    m = re.search(r"text-align\s*:\s*(left|right|center)", style or "", re.I)
    return m.group(1).lower() if m else None


def _table_from_soup(tbl) -> Table | None:
    """Build an IR Table from a bs4 <table>, scoped to THIS table's own rows/cells (so a nested
    table's rows aren't double-counted), recovering merged spans, header rows (<th>/<thead>), and
    nested tables (<table> inside a <td>) instead of flattening them to text."""
    rows: list[list[Cell]] = []
    header_first = False
    for tr in tbl.find_all("tr"):
        if tr.find_parent("table") is not tbl:        # belongs to a nested table
            continue
        cells: list[Cell] = []
        ths = 0
        for c in tr.find_all(["td", "th"]):
            if c.find_parent("table") is not tbl:     # cell of a nested table
                continue
            inner = c.find("table")
            nested = _table_from_soup(inner) if inner else None
            is_th = c.name == "th"
            ths += is_th
            cells.append(Cell(
                text="" if nested else c.get_text(" ", strip=True),
                rowspan=int(c.get("rowspan", 1) or 1),
                colspan=int(c.get("colspan", 1) or 1),
                bold=is_th or bool(c.find(["b", "strong"])),
                align=c.get("align") or _cell_align(c.get("style")),
                table=nested,
            ))
        if cells:
            if not rows and ths == len(cells):        # first row is all <th> -> header row
                header_first = True
            rows.append(cells)
    if not rows:
        return None
    return Table(rows=rows, has_header_row=header_first or tbl.find("thead") is not None)


def _parse_table_html(html: str) -> Table | None:
    """PP-StructureV3 emits each table as HTML; turn it into IR rows of Cells (translatable, grid +
    spans + header + nested tables preserved). Returns None if unparseable (caller then crops)."""
    if not html or "<" not in html:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    tbl = BeautifulSoup(html, "html.parser").find("table")
    return _table_from_soup(tbl) if tbl is not None else None
# Page furniture we drop from a clean reflow.
_SKIP = {"header", "footer", "number", "page_number", "formula_number", "header_image",
         "aside_text"}
# Regions that belong AFTER the body no matter what reading-order index the model gave them.
# PP-StructureV3 hands footnotes/references block_order=0 (it can't place a floating element),
# which would otherwise sort them to the very top of the page.
_LATE = {"footnote", "reference", "footnote_number"}


def _ordered_regions(regs: list) -> list:
    """Sort regions into reading order, robust to PP-StructureV3 giving floating elements
    (footnotes) block_order=0. If the model assigned real positive orders, any 0/None is
    treated as 'unplaced' and sinks below the ordered flow (by y-position); footnotes and
    references always sort after the body. If no region has a positive order, fall back to
    pure top-to-bottom position."""
    has_pos = any((r.order or 0) > 0 for r in regs)

    def key(r):
        o = r.order or 0
        if has_pos and o <= 0:
            o = 10_000          # model left it unplaced -> after the ordered flow
        return (1 if r.label in _LATE else 0, o, r.y0)

    return sorted(regs, key=key)


def _pick_text(digital: str, content: str) -> tuple[str, bool]:
    """Choose a region's text + whether the digital layer was usable. Prefer the digital text
    layer (perfect) — BUT only when it's real text: a subsetted/CID region with no ToUnicode emits
    "GLYPH<>"/replacement-char garbage, which the heuristic path OCRs but structured used to trust
    blindly. Fall back to the PP-OCR content when the digital layer is garbage or empty (audit P9).
    Also prefer OCR content when it carries inline-math LaTeX ($d_k$); the digital layer flattens
    it ("dk") and protect.py keeps the $...$ intact through translation."""
    from .pdf import _looks_garbage
    if "$" in content:
        return _INLINE_MATH.sub(lambda m: _clean_latex(m.group()), content), False
    digital_ok = bool(digital) and not _looks_garbage(digital)
    return (digital if digital_ok else content), digital_ok


def extract_structured(path: str, cfg: Config) -> Document:
    import fitz

    from ..layout.structure import get_structure_extractor

    doc = fitz.open(path)
    out = Document(source_path=path, mime="application/pdf", page_count=doc.page_count)
    out.metadata = {k: v for k, v in (doc.metadata or {}).items() if v}
    try:
        from ..ir import TocEntry
        out.toc = [TocEntry(level=int(lv), title=str(ti), page=int(pg))
                   for lv, ti, pg in (doc.get_toc() or [])]
    except Exception:
        pass
    for pno, page in enumerate(doc):
        out.page_sizes[pno] = (page.rect.width, page.rect.height)
        rot = int(getattr(page, "rotation", 0) or 0)   # carry /Rotate so review flags it
        if rot:
            out.page_rotation[pno] = rot

    from .pdf import _parse_pages
    selected = _parse_pages(getattr(cfg, "pages", None), doc.page_count)
    pnos = [p for p in range(doc.page_count) if selected is None or p in selected]
    regions_by_page = get_structure_extractor().extract_pages(doc, pnos)

    from .annots import capture as _capture_annots
    from .vectors import capture as _capture_vectors
    from .vectors import page_background as _page_bg

    img_dir = Path(tempfile.mkdtemp(prefix="transdoc_struct_"))
    out.tmp_dirs.append(str(img_dir))
    cidx = 0
    for pno in pnos:
        page = doc[pno]
        out.page_drawings[pno] = _capture_vectors(page)
        ann = _capture_annots(page)
        if ann:
            out.page_annots[pno] = ann
        bg = _page_bg(page)
        if bg:
            out.page_background[pno] = bg
        for r in _ordered_regions(regions_by_page.get(pno, [])):
            if r.label in _SKIP:
                continue
            bbox = BBox(x0=r.x0, y0=r.y0, x1=r.x1, y1=r.y1)
            if r.label == "table":
                tbl = _parse_table_html(r.content)
                if tbl:
                    out.blocks.append(Block(
                        id=f"p{pno}-r{r.order}", type=BlockType.TABLE, page=pno,
                        reading_order=len(out.blocks), bbox=bbox, table=tbl,
                        confidence=Confidence(source="digital")))
                    continue
                # parse failed -> fall through to a verbatim crop
            if r.label in _CROP or r.label == "table":
                rect = fitz.Rect(r.x0, r.y0, r.x1, r.y1)
                fn = img_dir / f"p{pno}-crop{cidx}.png"
                page.get_pixmap(clip=rect, dpi=200).save(str(fn))
                cidx += 1
                out.blocks.append(Block(
                    id=f"p{pno}-r{r.order}", type=BlockType.FIGURE, page=pno,
                    reading_order=len(out.blocks), bbox=bbox, crop_region=True, image_path=str(fn),
                    confidence=Confidence(source="digital")))
                # Optionally OCR text INSIDE the figure/chart (axis labels, callouts) so it gets
                # translated too — emitted as OCR blocks positioned within the figure bbox.
                if getattr(cfg, "ocr_figures", False) and r.label in ("image", "figure", "chart"):
                    _ocr_figure_region(out, page, rect, pno, cfg)
                continue
            if r.label == "formula":
                # Keep the LaTeX (Markdown renders it as $$…$$) AND a verbatim crop so
                # image-based outputs (DOCX/PDF) get pixel-perfect math.
                rect = fitz.Rect(r.x0, r.y0, r.x1, r.y1)
                fn = img_dir / f"p{pno}-formula{cidx}.png"
                try:
                    page.get_pixmap(clip=rect, dpi=200).save(str(fn))
                    fpath = str(fn)
                    cidx += 1
                except Exception:
                    fpath = None
                out.blocks.append(Block(
                    id=f"p{pno}-r{r.order}", type=BlockType.FORMULA, page=pno,
                    reading_order=len(out.blocks), bbox=bbox, text=_clean_latex(r.content.strip()),
                    image_path=fpath, confidence=Confidence(source="digital")))  # never translated
                continue
            digital = page.get_textbox(fitz.Rect(r.x0, r.y0, r.x1, r.y1)).strip()
            text, digital_ok = _pick_text(digital, r.content.strip())
            if not text:
                continue
            # bbox is always in PDF points here (parse_regions scales the 150-dpi render to
            # points), so the geometry source must stay "digital" — the renderers rescale a
            # block by 72/300 only when source=="ocr" (legacy 300-dpi pixel bboxes), which
            # would misplace this point-bbox. Carry true OCR provenance in a flag instead.
            blk = Block(
                id=f"p{pno}-r{r.order}", type=_LABEL.get(r.label, BlockType.PARAGRAPH),
                page=pno, reading_order=len(out.blocks), bbox=bbox, text=text,
                style=_region_style(page, fitz.Rect(r.x0, r.y0, r.x1, r.y1)),
                runs=_region_runs(page, fitz.Rect(r.x0, r.y0, r.x1, r.y1)) if digital_ok else [],
                confidence=Confidence(source="digital"))
            if not digital_ok:
                blk.flags["ocr_text"] = "text from PP-OCR (digital layer garbage/absent here)"
            out.blocks.append(blk)
    from .links import attach_pdf_links
    for pno in pnos:
        attach_pdf_links(doc[pno], [b for b in out.blocks if b.page == pno])

    doc.close()
    from .fuse import reconcile
    out.blocks = reconcile(out.blocks)
    # global reading order across pages
    for i, b in enumerate(sorted(out.blocks, key=lambda b: (b.page, b.reading_order))):
        b.reading_order = i
    from .base import associate_captions
    associate_captions(out)     # keep each caption adjacent to its figure/table
    out.blocks.sort(key=lambda b: b.reading_order)
    return out


_PT_TO_300 = 300.0 / 72.0


def _ocr_figure_region(out, page, rect, pno: int, cfg) -> None:
    """OCR text inside a figure/chart crop (axis labels, callouts) and emit it as translatable
    OCR blocks, bboxes mapped to the page in 300-dpi-pixel space (source='ocr' so the renderers
    scale them back to points). Skips tiny regions (icons) not worth OCRing."""
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    if abs(rect.width * rect.height) / page_area < 0.04:
        return
    try:
        from ..ocr import get_ocr
        pm = page.get_pixmap(clip=rect, dpi=300)
        ox, oy = rect.x0 * _PT_TO_300, rect.y0 * _PT_TO_300
        for ob in get_ocr(cfg).recognize_image_bytes(pm.tobytes("png"), cfg, page=pno):
            if ob.bbox:
                ob.bbox = BBox(x0=ob.bbox.x0 + ox, y0=ob.bbox.y0 + oy,
                               x1=ob.bbox.x1 + ox, y1=ob.bbox.y1 + oy)
            ob.reading_order = len(out.blocks)
            ob.flags["in_figure"] = "OCR'd from inside a figure/chart"
            out.blocks.append(ob)
    except Exception:
        pass


def _region_runs(page, rect):
    """Inline runs (mixed-style spans) for a region — reuses the heuristic span grouper."""
    from .pdf import _runs_from_spans
    try:
        lines = [ln for blk in page.get_text("dict", clip=rect)["blocks"]
                 for ln in blk.get("lines", [])]
        return _runs_from_spans(lines)
    except Exception:
        return []


def _region_style(page, rect) -> Style:
    """Dominant character style (font/size/colour/weight) of the digital spans inside a region,
    by char-count majority — so the structured path carries the same detail the heuristic PDF
    extractor does, instead of an empty Style. PyMuPDF span flags: bit 1 = italic, bit 4 = bold."""
    sizes: dict = {}
    fonts: dict = {}
    colors: dict = {}
    line_objs: list = []
    nchars = bold_chars = ital_chars = 0
    try:
        for b in page.get_text("dict", clip=rect)["blocks"]:
            for line in b.get("lines", []):
                line_objs.append(line)
                for s in line.get("spans", []):
                    n = len(s.get("text", "").strip())
                    if not n:
                        continue
                    nchars += n
                    # .get with defaults: a span missing size/font/colour must not throw and
                    # wipe the whole region's style via the outer except — fall back per-field.
                    sz = round(float(s.get("size", 0.0)), 1)
                    sizes[sz] = sizes.get(sz, 0) + n
                    fn = s.get("font") or "sans-serif"
                    fonts[fn] = fonts.get(fn, 0) + n
                    col = s.get("color", 0)
                    colors[col] = colors.get(col, 0) + n
                    fl = s.get("flags", 0)
                    if fl & 16:
                        bold_chars += n
                    if fl & 2:
                        ital_chars += n
    except Exception:
        return Style()
    if not nchars or not sizes:
        return Style()
    color = max(colors, key=colors.get)
    dom_size = max(sizes, key=sizes.get)
    from .pdf import _line_spacing
    return Style(font=max(fonts, key=fonts.get), size=dom_size or None,
                 color=f"#{color:06x}", bold=bold_chars > nchars / 2,
                 italic=ital_chars > nchars / 2,
                 line_spacing=_line_spacing(line_objs, dom_size))


