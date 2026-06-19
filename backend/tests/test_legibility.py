# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Legibility floor: when a translation only fits by shrinking below ~6pt, the overlay flags
the block 'illegible' (instead of silently shipping unreadable text), and the report counts
it and suggests a reflow."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Fidelity  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style  # noqa: E402
from transdoc.regenerate.pdf_out import render_overlay  # noqa: E402
from transdoc.report import build_report  # noqa: E402

_LONG = ("Sebuah terjemahan yang sangat panjang sekali sehingga mustahil muat di kotak "
         "mungil ini tanpa harus mengecil sampai tak terbaca lagi oleh siapa pun.")


def _doc(tmp_path):
    src = tmp_path / "s.pdf"
    d = fitz.open()
    d.new_page(width=300, height=400)
    d.save(str(src))
    doc = Document(source_path=str(src), mime="application/pdf", page_count=1)
    doc.page_sizes = {0: (300.0, 400.0)}
    a = Block(id="a", type=BlockType.PARAGRAPH, page=0, text="x",
              bbox=BBox(x0=20, y0=20, x1=80, y1=28), style=Style(size=9),
              confidence=Confidence(source="digital"))
    a.translated = _LONG
    blk = Block(id="b", type=BlockType.PARAGRAPH, page=0, text="y",      # blocks growth below
                bbox=BBox(x0=20, y0=30, x1=80, y1=38), style=Style(size=9),
                confidence=Confidence(source="digital"))
    blk.translated = "z"
    doc.blocks = [a, blk]
    return doc


def test_tiny_box_flags_illegible(tmp_path):
    doc = _doc(tmp_path)
    render_overlay(doc, Config(target_lang="id", fidelity=Fidelity.LAYOUT),
                   str(tmp_path / "o.pdf"))
    assert "illegible" in doc.blocks[0].flags


def test_report_counts_illegible(tmp_path):
    doc = _doc(tmp_path)
    render_overlay(doc, Config(target_lang="id", fidelity=Fidelity.LAYOUT),
                   str(tmp_path / "o.pdf"))
    report = build_report(doc, Config(target_lang="id"))
    assert "Rendering quality" in report
    assert "below readable size" in report
