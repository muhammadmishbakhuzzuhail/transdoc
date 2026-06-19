# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Strikethrough captured (docx) + rendered (md/docx/pdf), block + inline run."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Run, Style


def _blk(runs=None, strike=False):
    d = Document(source_path="x", mime="docx")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="deleted text", bbox=bb,
                      confidence=Confidence(), style=Style(strike=strike), runs=runs or [])]
    return d


def test_markdown_strike_block():
    from transdoc.regenerate.markdown import render
    # block-level strike applies via runs path; test inline run strike
    d = _blk(runs=[Run(text="gone", style=Style(strike=True))])
    assert "~~gone~~" in render(d, Config(target_lang="id"))


def test_pdf_run_span_strike():
    from transdoc.regenerate.pdf_out import _run_span
    assert "line-through" in _run_span(Run(text="x", style=Style(strike=True)))


def test_docx_strike(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.regenerate.docx_out import render
    out = tmp_path / "s.docx"
    render(_blk(runs=[Run(text="gone", style=Style(strike=True))]), Config(target_lang="id"),
           str(out))
    p = next(p for p in docx.Document(str(out)).paragraphs if p.text.strip())
    assert any(r.font.strike for r in p.runs)


def test_docx_extract_captures_strike(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    dd = docx.Document()
    para = dd.add_paragraph("keep ")
    run = para.add_run("struck")
    run.font.strike = True
    p = tmp_path / "x.docx"
    dd.save(str(p))
    doc = extract(str(p), Config(target_lang="id"))
    blk = next(b for b in doc.blocks if b.type == BlockType.PARAGRAPH)
    assert any(r.style.strike for r in blk.runs)
