# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Extraction dispatch: route a detected file Kind to the right extractor -> IR."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from ..config import Config
from ..ingest.detect import Detection, Kind, convert_to_docx
from ..ir import Document

log = logging.getLogger("transdoc.extract")


def _structured_enabled(cfg: Config) -> bool:
    """Whether to take the PP-StructureV3 structure path. On by default (layout=auto); forced off
    by TRANSDOC_LAYOUT_DISABLE=1 (tests set this for the fast, deterministic heuristic path)."""
    import os
    if os.environ.get("TRANSDOC_LAYOUT_DISABLE") == "1":
        return False
    return getattr(cfg, "layout", "off") in ("paddle", "auto")


def _is_non_latin_source(cfg: Config) -> bool:
    """True when the source is an explicit non-Latin language. PP-StructureV3's region OCR is rougher
    on non-Latin (merges words, more errors) than the digital det+rec path, so a non-Latin SCAN is
    better served by the line-OCR extractor. Explicit source only — an `auto` source isn't re-routed
    (its script isn't known until OCR)."""
    from ..ocr.router import LANG_TO_SCRIPT
    return (cfg.source_lang or "auto").lower() in LANG_TO_SCRIPT


def extract(det: Detection, cfg: Config) -> Document:
    k = det.kind
    p = str(det.path)

    if k == Kind.PDF_DIGITAL:
        # PP-StructureV3 structured path (formula->LaTeX, real table grids, precise formula/
        # figure regions, dedup, reading order) for PDF->Markdown/DOCX AND PDF->PDF. For PDF
        # output the reconstruct renderer crops formulas/figures verbatim and rebuilds tables
        # as translatable grids from the structured IR. Falls back to the standard extractor
        # if paddle is absent. SAME resolves to PDF here (this branch is PDF source).
        # An explicit non-Latin source skips PP-StructureV3: it re-OCRs the rendered page (ignoring
        # the PDF's own text layer) and its non-Latin OCR is rough — on the Arabic UDHR it returned
        # disconnected isolated letters where the clean text layer reads perfectly. The digital
        # extractor uses that text layer directly.
        from ..config import OutputFormat
        if (_structured_enabled(cfg) and not _is_non_latin_source(cfg)
                and cfg.output_format in (OutputFormat.MARKDOWN, OutputFormat.DOCX,
                                          OutputFormat.PDF, OutputFormat.SAME, OutputFormat.PLAIN)):
            try:
                from .structured import extract_structured
                return extract_structured(p, cfg)
            except Exception:
                log.warning("structured extraction failed for %s; falling back to the heuristic "
                            "extractor", p, exc_info=True)
        from .pdf import extract as ex
        return ex(p, cfg)
    if k == Kind.PDF_SCAN:
        # PP-StructureV3 also OCRs each region, so a scan gets the same structure-aware layout
        # (regions/tables/formula/reading-order) as a digital PDF — far better than line-OCR.
        # Falls back to the heuristic OCR path when paddle isn't reachable.
        # EXCEPT non-Latin scans: PP-StructureV3's region OCR is rougher there (word-merging, errors)
        # than the digital det+rec path, so route an explicit non-Latin source to line-OCR instead.
        if _structured_enabled(cfg) and not _is_non_latin_source(cfg):
            try:
                from .structured import extract_structured
                return extract_structured(p, cfg)
            except Exception:
                log.warning("structured extraction failed for scan %s; falling back to line-OCR",
                            p, exc_info=True)
        from .pdf import extract as ex
        import fitz
        with fitz.open(p) as _d:
            n = _d.page_count
        return ex(p, cfg, ocr_pages=set(range(n)))
    if k == Kind.PDF_MIXED:
        from ..ingest.detect import _image_dominates
        from .pdf import extract as ex
        import fitz
        # OCR the pages with no real text layer: empty/near-empty, OR a page whose text is
        # just a caption over a dominating scan image (matches detect._classify_pdf).
        with fitz.open(p) as d:
            ocr_pages = {i for i, pg in enumerate(d)
                         if len(pg.get_text().strip()) <= 20 or _image_dominates(pg)}
        return ex(p, cfg, ocr_pages=ocr_pages)
    if k == Kind.DOCX:
        from .docx import extract as ex
        return ex(p, cfg)
    if k in (Kind.DOC, Kind.RTF):
        tmpdir = Path(tempfile.mkdtemp())
        out = convert_to_docx(det.path, tmpdir)
        from .docx import extract as ex
        doc = ex(str(out), cfg)
        doc.tmp_dirs.append(str(tmpdir))   # else the converted .docx temp dir leaks every run
        return doc
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
                log.warning("structured extraction failed for image %s; falling back to line-OCR",
                            p, exc_info=True)
                if tmp:
                    import shutil
                    shutil.rmtree(tmp, ignore_errors=True)   # don't leak the orient temp dir
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
    if k == Kind.HTML:
        from .html import extract as ex
        return ex(p, cfg)
    if k == Kind.TEXT:
        from .text import extract as ex
        return ex(p, cfg)

    raise ValueError(f"no extractor for kind: {k} ({det.mime})")
