# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""bidi_mixed flag: detect mixed RTL+LTR lines and flag them in the overlay.

insert_htmlbox shapes each script but can misorder a line that mixes RTL + LTR runs
(PyMuPDF maintainer). We can't fix it in-renderer, so we flag the block for human review.
The detector is deliberately conservative — any RTL+Latin mix is flagged.
"""

from __future__ import annotations

import fitz

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style
from transdoc.regenerate.pdf_out import _is_mixed_bidi, render_overlay


def test_detector_flags_only_mixed_lines():
    assert _is_mixed_bidi("Hello world") is False        # pure Latin
    assert _is_mixed_bidi("مرحبا بالعالم") is False       # pure Arabic
    assert _is_mixed_bidi("مرحبا 123") is False           # Arabic + digits only
    assert _is_mixed_bidi("مرحبا Google بالعالم") is True  # Arabic + Latin
    assert _is_mixed_bidi("שלום World") is True            # Hebrew + Latin


def _pdf_block(tmp_path, translated: str) -> tuple[Document, Block]:
    src = tmp_path / "src.pdf"
    doc_pdf = fitz.open()
    doc_pdf.new_page(width=420, height=120).insert_text((40, 60), "Original line", fontsize=12)
    doc_pdf.save(str(src))
    doc_pdf.close()

    b = Block(id="a", type=BlockType.PARAGRAPH, page=0, text="x", translated=translated,
              bbox=BBox(x0=40, y0=48, x1=380, y1=72),
              confidence=Confidence(source="digital"), style=Style(rtl=True, size=12))
    doc = Document(source_path=str(src), mime="application/pdf")
    doc.blocks = [b]
    return doc, b


def test_overlay_flags_mixed_block(tmp_path):
    doc, b = _pdf_block(tmp_path, "زوروا https://example.com اليوم")
    render_overlay(doc, Config(target_lang="ar"), str(tmp_path / "out.pdf"))
    assert "bidi_mixed" in b.flags


def test_overlay_does_not_flag_pure_rtl(tmp_path):
    doc, b = _pdf_block(tmp_path, "هذا النص باللغة العربية فقط")
    render_overlay(doc, Config(target_lang="ar"), str(tmp_path / "out.pdf"))
    assert "bidi_mixed" not in b.flags
