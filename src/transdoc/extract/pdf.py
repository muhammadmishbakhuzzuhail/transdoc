"""PDF extraction via PyMuPDF.

Digital PDFs: pull text blocks with bbox + font/size so we can infer headings and keep
layout. Scanned / mixed PDFs: rasterize the image-only pages and hand them to OCR.
"""

from __future__ import annotations

import re
import unicodedata

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Document, Style
from .base import block_id, reflow_order

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
    ctrl = sum(1 for c in s if c not in "\t\n\r" and unicodedata.category(c) in _BAD_CATS)
    return ctrl / len(s) > _GARBAGE_CTRL


def _parse_pages(spec: str | None, total: int) -> set[int] | None:
    """Parse a 1-based page selection ("3-7,10,15-") to a 0-based index set. None -> all."""
    if not spec or not spec.strip():
        return None
    sel: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            start = int(a) if a.strip() else 1
            end = int(b) if b.strip() else total
        else:
            start = end = int(part)
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

    selected = _parse_pages(getattr(cfg, "pages", None), doc.page_count)
    ocr = get_ocr(cfg) if ocr_pages else None
    img_dir = Path(tempfile.mkdtemp(prefix="transdoc_img_"))

    def _ensure_ocr():
        nonlocal ocr
        if ocr is None:
            ocr = get_ocr(cfg)
        return ocr

    def _ocr_page(page, pno) -> None:
        eng = _ensure_ocr()
        pix = page.get_pixmap(dpi=300)
        out.blocks.extend(eng.recognize_image_bytes(pix.tobytes("png"), cfg, page=pno))

    for pno, page in enumerate(doc):
        out.page_sizes[pno] = (page.rect.width, page.rect.height)

        if selected is not None and pno not in selected:
            continue  # page not in the requested selection — skip extraction/translation

        if pno in ocr_pages:
            _ocr_page(page, pno)
            continue

        # Trust digital text only if it isn't CID-font garbage; otherwise OCR the page.
        if _looks_garbage(page.get_text()):
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
            bold = italic = False
            # Carry the font + colour of the dominant (largest) span so the overlay can
            # reproduce them — keeping the page's look (bold/italic/colour), not just size.
            dom_size = -1.0
            font: str | None = None
            color: str | None = None
            for line in lines:
                for span in line.get("spans", []):
                    text_parts.append(span.get("text", ""))
                    sz = span.get("size", 0)
                    max_size = max(max_size, sz)
                    flags = span.get("flags", 0)
                    if flags & 2 ** 4:   # bold
                        bold = True
                    if flags & 2 ** 1:   # italic
                        italic = True
                    if sz > dom_size and span.get("text", "").strip():
                        dom_size = sz
                        font = span.get("font") or font
                        c = span.get("color")
                        if isinstance(c, int):
                            color = f"#{c & 0xFFFFFF:06x}"
                text_parts.append(" ")
            text = _dehyphenate("".join(text_parts).strip())
            if not text:
                continue
            x0, y0, x1, y1 = blk["bbox"]
            if _looks_formula(text):
                btype = BlockType.FORMULA
            elif _looks_tabular(text):
                btype = BlockType.TABLE  # merged numeric table rows -> preserve verbatim
            else:
                btype = _guess_type(max_size, body, 0)
            out.blocks.append(
                Block(
                    id=block_id(pno, idx),
                    type=btype,
                    page=pno,
                    text=text,
                    bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1),
                    style=Style(size=max_size, bold=bold, italic=italic, font=font,
                                color=color,
                                heading_level=1 if btype == BlockType.HEADING else 0),
                    confidence=Confidence(source="digital"),
                )
            )
            idx += 1

    doc.close()
    reflow_order(out)
    return out
