# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Overlay box-expand: a long translation in a short box grows down into empty space (keeps
font size, no shrink flag); if a block sits right below, it can't grow and shrinks instead."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Fidelity  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style  # noqa: E402
from transdoc.regenerate.pdf_out import render_overlay  # noqa: E402

_LONG = ("Sebuah kalimat terjemahan yang jauh lebih panjang dari aslinya sehingga "
         "membutuhkan ruang tambahan yang banyak supaya tetap terbaca dengan jelas ya.")


def _make(tmp_path, crowded: bool):
    src = tmp_path / "s.pdf"
    d = fitz.open()
    d.new_page(width=300, height=400)
    d.save(str(src))
    doc = Document(source_path=str(src), mime="application/pdf", page_count=1)
    doc.page_sizes = {0: (300.0, 400.0)}
    a = Block(id="a", type=BlockType.PARAGRAPH, page=0, text="src",
              bbox=BBox(x0=20, y0=20, x1=120, y1=33), style=Style(size=11),
              confidence=Confidence(source="digital"))
    a.translated = _LONG
    doc.blocks = [a]
    if crowded:                       # a block immediately below blocks downward growth
        b = Block(id="b", type=BlockType.PARAGRAPH, page=0, text="below",
                  bbox=BBox(x0=20, y0=40, x1=120, y1=53), style=Style(size=11),
                  confidence=Confidence(source="digital"))
        b.translated = "x"
        doc.blocks.append(b)
    out = tmp_path / "o.pdf"
    render_overlay(doc, Config(target_lang="id", fidelity=Fidelity.LAYOUT), str(out))
    return doc.blocks[0]


def test_grows_into_whitespace_no_shrink(tmp_path):
    block = _make(tmp_path, crowded=False)
    assert "text_expansion" not in block.flags     # grew down, no hard shrink


def test_blocked_below_falls_back_to_shrink(tmp_path):
    block = _make(tmp_path, crowded=True)
    # no room to grow -> shrinks to fit -> flagged (text_expansion if still legible, or
    # illegible if it had to shrink below the readable floor)
    assert "text_expansion" in block.flags or "illegible" in block.flags
