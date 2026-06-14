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


def _parse_table_html(html: str) -> Table | None:
    """PP-StructureV3 emits each table as HTML; turn it into IR rows of Cells (translatable,
    grid preserved). Returns None if it can't be parsed (caller then crops the region)."""
    if not html or "<" not in html:
        return None
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None
    soup = BeautifulSoup(html, "html.parser")
    rows: list[list[Cell]] = []
    for tr in soup.find_all("tr"):
        cells = [Cell(text=td.get_text(" ", strip=True),
                      rowspan=int(td.get("rowspan", 1) or 1),
                      colspan=int(td.get("colspan", 1) or 1))
                 for td in tr.find_all(["td", "th"])]
        if cells:
            rows.append(cells)
    return Table(rows=rows) if rows else None
# Page furniture we drop from a clean reflow.
_SKIP = {"header", "footer", "number", "page_number", "formula_number", "header_image",
         "aside_text"}


def extract_structured(path: str, cfg: Config) -> Document:
    import fitz

    from ..layout.structure import get_structure_extractor

    doc = fitz.open(path)
    out = Document(source_path=path, mime="application/pdf", page_count=doc.page_count)
    for pno, page in enumerate(doc):
        out.page_sizes[pno] = (page.rect.width, page.rect.height)

    from .pdf import _parse_pages
    selected = _parse_pages(getattr(cfg, "pages", None), doc.page_count)
    pnos = [p for p in range(doc.page_count) if selected is None or p in selected]
    regions_by_page = get_structure_extractor().extract_pages(doc, pnos)

    img_dir = Path(tempfile.mkdtemp(prefix="transdoc_struct_"))
    cidx = 0
    for pno in pnos:
        page = doc[pno]
        for r in sorted(regions_by_page.get(pno, []), key=lambda r: ((r.order or 0), r.y0)):
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
            # text-like: prefer the digital text layer (perfect); fall back to OCR content
            digital = page.get_textbox(fitz.Rect(r.x0, r.y0, r.x1, r.y1)).strip()
            content = r.content.strip()
            # Prefer the OCR content when it carries inline math LaTeX ($d_k$ etc.) — the
            # digital text layer flattens it ("dk"). protect.py masks $...$ during translation
            # so the MT engine leaves it intact. Plain prose uses the clean digital layer.
            if "$" in content:
                # clean letter-spacing only inside the inline-math spans; leave prose untouched
                text = _INLINE_MATH.sub(lambda m: _clean_latex(m.group()), content)
            else:
                text = digital or content
            if not text:
                continue
            # bbox is always in PDF points here (parse_regions scales the 150-dpi render to
            # points), so the geometry source must stay "digital" — the renderers rescale a
            # block by 72/300 only when source=="ocr" (legacy 300-dpi pixel bboxes), which
            # would misplace this point-bbox. Carry true OCR provenance in a flag instead.
            blk = Block(
                id=f"p{pno}-r{r.order}", type=_LABEL.get(r.label, BlockType.PARAGRAPH),
                page=pno, reading_order=len(out.blocks), bbox=bbox, text=text,
                style=Style(), confidence=Confidence(source="digital"))
            if not digital:
                blk.flags["ocr_text"] = "text from PP-OCR (no digital layer in this region)"
            out.blocks.append(blk)
    doc.close()
    out.blocks = _dedup(out.blocks)
    # global reading order across pages
    for i, b in enumerate(sorted(out.blocks, key=lambda b: (b.page, b.reading_order))):
        b.reading_order = i
    out.blocks.sort(key=lambda b: b.reading_order)
    return out


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _dedup(blocks: list[Block]) -> list[Block]:
    """PP-StructureV3 sometimes returns overlapping text regions -> duplicated prose. Drop a
    text block whose normalized text duplicates (or is contained in) another's; keep the longer.
    Non-text blocks (figures/formulas/tables) are never deduped."""
    text_types = {BlockType.PARAGRAPH, BlockType.HEADING, BlockType.TITLE, BlockType.CAPTION}
    kept: list[Block] = []
    norms: list[str] = []
    for b in blocks:
        if b.type not in text_types or len(_norm(b.text)) < 15:
            kept.append(b)
            norms.append("")
            continue
        n = _norm(b.text)
        dup_at = -1
        for i, kn in enumerate(norms):
            if not kn:
                continue
            if n == kn or (len(n) > 20 and n in kn) or (len(kn) > 20 and kn in n):
                dup_at = i
                break
        if dup_at == -1:
            kept.append(b)
            norms.append(n)
        elif len(n) > len(norms[dup_at]):     # keep the longer/more complete version
            kept[dup_at] = b
            norms[dup_at] = n
    return kept
