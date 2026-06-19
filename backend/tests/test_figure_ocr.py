# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""OCR text inside figures (opt-in): blocks mapped into the figure bbox, flagged in_figure, and
NOT dropped by reconcile (they intentionally sit inside the figure region)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence


def test_reconcile_keeps_in_figure_blocks():
    from transdoc.extract.fuse import reconcile
    fig = Block(id="f", type=BlockType.FIGURE, bbox=BBox(x0=0, y0=0, x1=400, y1=400),
                confidence=Confidence())
    label = Block(id="l", type=BlockType.CAPTION, text="Axis label", page=0,
                  bbox=BBox(x0=10, y0=10, x1=80, y1=25),
                  flags={"in_figure": "x"}, confidence=Confidence(source="ocr"))
    out = reconcile([fig, label])
    assert {b.id for b in out} == {"f", "l"}     # figure-OCR label survives


def test_ocr_figure_region_maps_and_flags(monkeypatch):
    fitz = pytest.importorskip("fitz")
    import transdoc.ocr as OCRMOD
    from transdoc.extract import structured
    from transdoc.ir import Document

    class _FakeOCR:
        def recognize_image_bytes(self, img, cfg, page=0):
            return [Block(id="t", type=BlockType.PARAGRAPH, text="label", page=page,
                          bbox=BBox(x0=30, y0=30, x1=90, y1=50),
                          confidence=Confidence(source="ocr", ocr=0.9))]

    monkeypatch.setattr(OCRMOD, "get_ocr", lambda cfg: _FakeOCR())
    d = fitz.open()
    pg = d.new_page(width=600, height=600)
    out = Document(source_path="x", mime="application/pdf")
    structured._ocr_figure_region(out, pg, fitz.Rect(100, 100, 500, 500), 0, Config(target_lang="id"))
    d.close()
    assert out.blocks, "figure OCR should emit a block"
    b = out.blocks[0]
    # bbox offset by region origin in 300-dpi pixels (100pt * 300/72 ~= 416.7)
    assert b.bbox.x0 > 400 and "in_figure" in b.flags


def test_ocr_figure_region_skips_tiny(monkeypatch):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract import structured
    from transdoc.ir import Document
    d = fitz.open()
    pg = d.new_page(width=600, height=600)
    out = Document(source_path="x", mime="application/pdf")
    # tiny region (<4% of page) -> skipped, no OCR call
    structured._ocr_figure_region(out, pg, fitz.Rect(0, 0, 50, 50), 0, Config(target_lang="id"))
    d.close()
    assert out.blocks == []
