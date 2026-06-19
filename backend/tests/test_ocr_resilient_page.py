# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""A single page's OCR failure must not sink the whole document (audit P1 edge-case)."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402


class _BoomOCR:
    name = "boom"

    def recognize_image_bytes(self, img, cfg, page=0):
        raise RuntimeError("ocr engine exploded on this page")


def test_ocr_page_failure_is_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("transdoc.ocr.get_ocr", lambda cfg: _BoomOCR())
    d = fitz.open()
    for _ in range(2):
        d.new_page(width=400, height=400)
    path = tmp_path / "scan.pdf"
    d.save(str(path))
    d.close()
    # ocr_pages both pages; OCR raises -> must not crash, returns a Document
    doc = extract(str(path), Config(target_lang="id"), ocr_pages={0, 1})
    assert doc.page_count == 2   # survived, no exception
