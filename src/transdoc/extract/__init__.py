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
        from .pdf import extract as ex
        return ex(p, cfg)
    if k == Kind.PDF_SCAN:
        from .pdf import extract as ex
        import fitz
        n = fitz.open(p).page_count
        return ex(p, cfg, ocr_pages=set(range(n)))
    if k == Kind.PDF_MIXED:
        from .pdf import extract as ex
        import fitz
        d = fitz.open(p)
        ocr_pages = {i for i, pg in enumerate(d) if len(pg.get_text().strip()) <= 20}
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
    if k in (Kind.TEXT, Kind.HTML):
        from .text import extract as ex
        return ex(p, cfg)

    raise ValueError(f"no extractor for kind: {k} ({det.mime})")
