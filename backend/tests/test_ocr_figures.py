# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""OCR-in-figure: text inside a large embedded image (a scan dropped on a digital page) is
recovered as translatable OCR blocks only when cfg.ocr_figures is set (default off = no
perf cost), and its bbox is mapped onto the page."""

from __future__ import annotations

import shutil

import pytest

fitz = pytest.importorskip("fitz")

if not shutil.which("tesseract"):
    pytest.skip("tesseract not installed", allow_module_level=True)

from transdoc.config import Config, OutputFormat  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402


def _digital_page_with_text_image(path: str) -> None:
    timg = fitz.open()
    tp = timg.new_page(width=300, height=120)
    tp.insert_text((10, 60), "SCANNED INVOICE TOTAL", fontsize=18)
    pix = tp.get_pixmap(dpi=150)
    doc = fitz.open()
    pg = doc.new_page(width=400, height=500)
    pg.insert_text((40, 40), "Digital heading on the page here", fontsize=14)
    pg.insert_image(fitz.Rect(40, 100, 360, 360), pixmap=pix)   # big embedded image
    doc.save(path)


def test_figure_ocr_off_by_default(tmp_path):
    src = tmp_path / "f.pdf"
    _digital_page_with_text_image(str(src))
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.PDF))
    assert not [b for b in doc.blocks if b.confidence.source == "ocr"]


def test_figure_ocr_recovers_text_when_enabled(tmp_path):
    src = tmp_path / "f.pdf"
    _digital_page_with_text_image(str(src))
    doc = extract(str(src),
                  Config(target_lang="id", output_format=OutputFormat.PDF, ocr_figures=True))
    ocr = [b for b in doc.blocks if b.confidence.source == "ocr"]
    assert ocr, "expected OCR text recovered from the embedded image"
    assert any("INVOICE" in b.text.upper() for b in ocr)
    # bbox mapped into the image region (300-dpi pixel space: image starts at x=40pt -> ~166px)
    assert all(b.bbox and b.bbox.x0 > 100 for b in ocr if b.bbox)
