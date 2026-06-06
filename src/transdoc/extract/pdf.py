"""PDF extraction via PyMuPDF.

Digital PDFs: pull text blocks with bbox + font/size so we can infer headings and keep
layout. Scanned / mixed PDFs: rasterize the image-only pages and hand them to OCR.
"""

from __future__ import annotations

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Document, Style
from .base import block_id, reflow_order


def _guess_type(size: float, body_size: float, flags: int) -> BlockType:
    """Heuristic: larger-than-body font -> heading; much larger -> title."""
    if size >= body_size * 1.6:
        return BlockType.TITLE
    if size >= body_size * 1.2:
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
    doc = fitz.open(path)
    out = Document(source_path=path, mime="application/pdf", page_count=doc.page_count)

    ocr = get_ocr(cfg) if ocr_pages else None
    img_dir = Path(tempfile.mkdtemp(prefix="transdoc_img_"))

    for pno, page in enumerate(doc):
        out.page_sizes[pno] = (page.rect.width, page.rect.height)

        if pno in ocr_pages:
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            ocr_blocks = ocr.recognize_image_bytes(img_bytes, cfg, page=pno)
            out.blocks.extend(ocr_blocks)
            continue

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
            except Exception:
                continue

        body = _body_size(page)
        d = page.get_text("dict")
        idx = 0
        for blk in d.get("blocks", []):
            lines = blk.get("lines", [])
            if not lines:
                continue
            text_parts: list[str] = []
            max_size = 0.0
            bold = False
            for line in lines:
                for span in line.get("spans", []):
                    text_parts.append(span.get("text", ""))
                    max_size = max(max_size, span.get("size", 0))
                    if span.get("flags", 0) & 2 ** 4:  # bold flag
                        bold = True
                text_parts.append(" ")
            text = "".join(text_parts).strip()
            if not text:
                continue
            x0, y0, x1, y1 = blk["bbox"]
            btype = _guess_type(max_size, body, 0)
            out.blocks.append(
                Block(
                    id=block_id(pno, idx),
                    type=btype,
                    page=pno,
                    text=text,
                    bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    style=Style(size=max_size, bold=bold,
                                heading_level=1 if btype == BlockType.HEADING else 0),
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1

    doc.close()
    reflow_order(out)
    return out
