"""Extraction dispatch: route a detected file Kind to the right extractor -> IR."""

from __future__ import annotations

import tempfile
from pathlib import Path

from ..config import Config
from ..ingest.detect import Detection, Kind, convert_to_docx
from ..ir import Document


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
        if (getattr(cfg, "layout", "off") in ("paddle", "auto")
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
