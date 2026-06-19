# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""All-caps run styling captured (docx) + rendered (md/docx/pdf)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Run, Style


def _blk():
    d = Document(source_path="x", mime="docx")
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="loud", bbox=BBox(x0=0,y0=0,x1=1,y1=1),
                      confidence=Confidence(), runs=[Run(text="loud", style=Style(all_caps=True))])]
    return d


def test_markdown_allcaps_upper():
    from transdoc.regenerate.markdown import render
    assert "LOUD" in render(_blk(), Config(target_lang="id"))


def test_pdf_allcaps_css():
    from transdoc.regenerate.pdf_out import _run_span
    assert "text-transform:uppercase" in _run_span(_blk().blocks[0].runs[0])


def test_docx_extract_allcaps(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    dd = docx.Document()
    para = dd.add_paragraph("a ")
    para.add_run("CAPS").font.all_caps = True
    p = tmp_path / "x.docx"
    dd.save(str(p))
    blk = next(b for b in extract(str(p), Config(target_lang="id")).blocks
               if b.type == BlockType.PARAGRAPH)
    assert any(r.style.all_caps for r in blk.runs)
