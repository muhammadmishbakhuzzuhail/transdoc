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


def _page_is_multicolumn(pg) -> bool:
    """Cheap per-page column check on raw PyMuPDF text blocks (no models): >=2 side-by-side
    column clusters, each < 60% page width, that vertically overlap. Mirrors
    pipeline._is_multicolumn but pre-extraction."""
    blocks = [b for b in pg.get_text("blocks") if b[4].strip()]
    if len(blocks) < 4:
        return False
    pw = pg.rect.width or 595.0
    cols: list[dict] = []
    for b in sorted(blocks, key=lambda x: x[0]):
        x0, x1 = b[0], b[2]
        for c in cols:
            if min(c["x1"], x1) - max(c["x0"], x0) > 0.3 * min(c["x1"] - c["x0"], x1 - x0):
                c["x0"], c["x1"] = min(c["x0"], x0), max(c["x1"], x1)
                c["bs"].append(b)
                break
        else:
            cols.append({"x0": x0, "x1": x1, "bs": [b]})
    real = [c for c in cols if len(c["bs"]) >= 2 and (c["x1"] - c["x0"]) < 0.6 * pw]
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            a, bb = real[i]["bs"], real[j]["bs"]
            ay0, ay1 = min(x[1] for x in a), max(x[3] for x in a)
            by0, by1 = min(x[1] for x in bb), max(x[3] for x in bb)
            if min(ay1, by1) - max(ay0, by0) > 0.4 * min(ay1 - ay0, by1 - by0):
                return True
    return False


def _is_simple_digital_pdf(path: str) -> bool:
    """A clean single-column text PDF with no figures/tables gains little from PP-StructureV3 but
    pays its ~30s paddle cold-load (the dominant cost — profiled 40s extract vs 7s heuristic).
    Cheaply pre-scan with no models: return True (use the fast heuristic extractor) ONLY when the
    doc has NO raster image on any page AND every page is single-column. Conservative — any image
    or any multi-column page keeps the structured path, so figure/table/column docs are unaffected.
    On any error, return False (keep structured)."""
    import os

    import fitz
    if os.environ.get("TRANSDOC_SIMPLE_SKIP_DISABLE") == "1":
        return False
    try:
        with fitz.open(path) as d:
            for pg in d:
                if pg.get_images() or _page_is_multicolumn(pg):
                    return False
        return True
    except Exception:
        return False


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
                and not _is_simple_digital_pdf(p)        # clean single-col, no figures -> skip the
                                                         # ~30s paddle cold-load, heuristic suffices
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
