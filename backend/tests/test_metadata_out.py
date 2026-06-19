# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Source metadata (title/author) written to output PDF + DOCX (audit ◐ -> ✓)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _doc():
    d = Document(source_path="x", mime="application/pdf", page_count=1)
    d.page_sizes[0] = (595.0, 842.0)
    d.metadata = {"title": "My Title", "author": "Jane Doe"}
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="body text here",
                      bbox=BBox(x0=40, y0=60, x1=400, y1=90), confidence=Confidence())]
    return d


def test_pdf_metadata_written(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.regenerate.pdf_out import render_reconstruct
    out = tmp_path / "o.pdf"
    render_reconstruct(_doc(), Config(target_lang="id"), str(out))
    m = fitz.open(str(out)).metadata
    assert m.get("title") == "My Title" and m.get("author") == "Jane Doe"


def test_docx_metadata_written(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.regenerate.docx_out import render
    out = tmp_path / "o.docx"
    render(_doc(), Config(target_lang="id"), str(out))
    cp = docx.Document(str(out)).core_properties
    assert cp.title == "My Title" and cp.author == "Jane Doe"
