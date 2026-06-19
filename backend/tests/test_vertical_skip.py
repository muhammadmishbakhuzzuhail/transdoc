# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Vertical/rotated text (e.g. an arXiv ID sidebar) is left untranslated in the PDF overlay
instead of being redacted and shrunk to an illegible sliver."""

from __future__ import annotations

import fitz

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style
from transdoc.regenerate.pdf_out import render_overlay


def _pdf(tmp_path):
    src = tmp_path / "s.pdf"
    d = fitz.open()
    d.new_page(width=600, height=800)
    d.save(str(src))
    d.close()
    return str(src)


def _blk(bid, bbox):
    return Block(id=bid, type=BlockType.PARAGRAPH, page=0, text="hello world",
                 translated="halo dunia", bbox=BBox(**bbox),
                 confidence=Confidence(source="digital"), style=Style())


def test_vertical_block_left_untranslated(tmp_path):
    doc = Document(source_path=_pdf(tmp_path), mime="application/pdf")
    vertical = _blk("v", dict(x0=20, y0=100, x1=34, y1=700))   # tall + 14pt wide
    normal = _blk("n", dict(x0=80, y0=100, x1=400, y1=130))    # wide line
    doc.blocks = [vertical, normal]
    render_overlay(doc, Config(target_lang="id"), str(tmp_path / "o.pdf"))
    assert "rotated_text" in vertical.flags
    assert "rotated_text" not in normal.flags
