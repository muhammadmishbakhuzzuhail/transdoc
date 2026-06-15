"""Extraction dispatch: route a detected file Kind to the right extractor -> IR."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..config import Config
from ..ingest.detect import Detection, Kind, convert_to_docx
from ..ir import Document


def _structured_enabled(cfg: Config) -> bool:
    """Whether to take the PP-StructureV3 structure path. On by default (layout=auto); forced off
    by TRANSDOC_LAYOUT_DISABLE=1 (tests set this for the fast, deterministic heuristic path)."""
    import os
    if os.environ.get("TRANSDOC_LAYOUT_DISABLE") == "1":
        return False
    return getattr(cfg, "layout", "off") in ("paddle", "auto")


def extract(det: Detection, cfg: Config) -> Document:
    k = det.kind
    p = str(det.path)

    if k == Kind.PDF_DIGITAL:
        # PP-StructureV3 structured path (formula->LaTeX, real table grids, precise formula/
        # figure regions, dedup, reading order) for PDF->Markdown/DOCX AND PDF->PDF. For PDF
        # output the reconstruct renderer crops formulas/figures verbatim and rebuilds tables
        # as translatable grids from the structured IR. Falls back to the standard extractor
        # if paddle is absent. SAME resolves to PDF here (this branch is PDF source).
        from ..config import OutputFormat
        if (_structured_enabled(cfg)
                and cfg.output_format in (OutputFormat.MARKDOWN, OutputFormat.DOCX,
                                          OutputFormat.PDF, OutputFormat.SAME, OutputFormat.PLAIN)):
            try:
                from .structured import extract_structured
                return extract_structured(p, cfg)
            except Exception:
                pass
        from .pdf import extract as ex
        return ex(p, cfg)
    if k == Kind.PDF_SCAN:
        # PP-StructureV3 also OCRs each region, so a scan gets the same structure-aware layout
        # (regions/tables/formula/reading-order) as a digital PDF — far better than line-OCR.
        # Falls back to the heuristic OCR path when paddle isn't reachable.
        if _structured_enabled(cfg):
            try:
                from .structured import extract_structured
                return extract_structured(p, cfg)
            except Exception:
                pass
        from .pdf import extract as ex
        import fitz
        n = fitz.open(p).page_count
        return ex(p, cfg, ocr_pages=set(range(n)))
    if k == Kind.PDF_MIXED:
        from ..ingest.detect import _image_dominates
        from .pdf import extract as ex
        import fitz
        d = fitz.open(p)
        # OCR the pages with no real text layer: empty/near-empty, OR a page whose text is
        # just a caption over a dominating scan image (matches detect._classify_pdf).
        ocr_pages = {i for i, pg in enumerate(d)
                     if len(pg.get_text().strip()) <= 20 or _image_dominates(pg)}
        d.close()
        return ex(p, cfg, ocr_pages=ocr_pages)
    if k == Kind.DOCX:
        from .docx import extract as ex
        return ex(p, cfg)
    if k in (Kind.DOC, Kind.RTF):
        out = convert_to_docx(det.path, Path(tempfile.mkdtemp()))
        from .docx import extract as ex
        return ex(str(out), cfg)
    if k == Kind.ODT:
        from .odt import extract as ex
        return ex(p, cfg)
    if k == Kind.IMAGE:
        # A standalone image is a scan too: route it through PP-StructureV3 so it gets the same
        # structure-aware layout (headings/tables/figures/reading-order) as a scanned PDF, instead
        # of flat line-OCR paragraphs (audit: a newspaper JPG came out as 60 untyped paragraphs
        # with the masthead lost; structured gives titles/headings + the masthead figure). Only
        # for text outputs that rebuild from the IR — image->image/PDF overlay still needs the
        # raster path's deskewed render_path. Falls back to line-OCR on any failure (e.g. GPU OOM).
        from ..config import OutputFormat
        if (_structured_enabled(cfg)
                and cfg.output_format in (OutputFormat.MARKDOWN, OutputFormat.DOCX,
                                          OutputFormat.PLAIN)):
            from pathlib import Path as _Path

            from .image import _coarse_orient
            oriented, rot = _coarse_orient(_Path(p).read_bytes())   # upright before layout
            src, tmp = p, None
            if rot:
                tmp = tempfile.mkdtemp(prefix="transdoc_orient_")
                src = str(_Path(tmp) / "oriented.png")
                _Path(src).write_bytes(oriented)
            try:
                from .structured import extract_structured
                doc = extract_structured(src, cfg)
                doc.mime = "image"            # image source, not a real PDF
                doc.source_path = p
                if tmp:
                    doc.tmp_dirs.append(tmp)
                return doc
            except Exception:
                pass
        from .image import extract as ex
        return ex(p, cfg)
    if k == Kind.PPTX:
        from .pptx import extract as ex
        return ex(p, cfg)
    if k == Kind.XLSX:
        from .xlsx import extract as ex
        return ex(p, cfg)
    if k == Kind.EPUB:
        from .epub import extract as ex
        return ex(p, cfg)
    if k in (Kind.SRT, Kind.VTT):
        from .subtitle import extract as ex
        return ex(p, cfg)
    if k in (Kind.TEXT, Kind.HTML):
        from .text import extract as ex
        return ex(p, cfg)

    raise ValueError(f"no extractor for kind: {k} ({det.mime})")
