"""Structured PDF extraction via PP-StructureV3: build the IR straight from detected regions,
keeping **formulas as LaTeX** and figures/tables/seals as verbatim crops. Text regions use the
digital text layer when present (perfect), falling back to the region's OCR content (scans).

Phase 1 target: PDF -> Markdown. Tables and images are emitted as cropped pictures for now;
table-HTML -> cells is a later phase. See ppstructurev3-region-router."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Document, Style

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
# Regions cropped verbatim from the source (no text reflow).
_CROP = {"image", "figure", "chart", "table", "seal", "stamp"}
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
            if r.label in _CROP:
                rect = fitz.Rect(r.x0, r.y0, r.x1, r.y1)
                fn = img_dir / f"p{pno}-crop{cidx}.png"
                page.get_pixmap(clip=rect, dpi=200).save(str(fn))
                cidx += 1
                out.blocks.append(Block(
                    id=f"p{pno}-r{r.order}", type=BlockType.FIGURE, page=pno,
                    reading_order=r.order, bbox=bbox, crop_region=True, image_path=str(fn),
                    confidence=Confidence(source="digital")))
                continue
            if r.label == "formula":
                out.blocks.append(Block(
                    id=f"p{pno}-r{r.order}", type=BlockType.FORMULA, page=pno,
                    reading_order=r.order, bbox=bbox, text=r.content.strip(),
                    confidence=Confidence(source="digital")))  # LaTeX, never translated
                continue
            # text-like: prefer the digital text layer (perfect); fall back to OCR content
            digital = page.get_textbox(fitz.Rect(r.x0, r.y0, r.x1, r.y1)).strip()
            text = digital or r.content.strip()
            if not text:
                continue
            out.blocks.append(Block(
                id=f"p{pno}-r{r.order}", type=_LABEL.get(r.label, BlockType.PARAGRAPH),
                page=pno, reading_order=r.order, bbox=bbox, text=text,
                style=Style(), confidence=Confidence(source="digital" if digital else "ocr")))
    doc.close()
    # global reading order across pages
    for i, b in enumerate(sorted(out.blocks, key=lambda b: (b.page, b.reading_order))):
        b.reading_order = i
    out.blocks.sort(key=lambda b: b.reading_order)
    return out
