"""Inline run-level styling: capture mixed-style docx paragraph -> translate per-run -> render
bold/super/link inline in markdown + docx. Uniform paragraphs keep runs empty (no change)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Run, Style


def _mixed_block():
    d = Document(source_path="x", mime="docx")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="see API now", bbox=bb,
                      confidence=Confidence(), runs=[
                          Run(text="see ", style=Style()),
                          Run(text="API", style=Style(bold=True)),
                          Run(text=" now", style=Style(superscript=True))])]
    return d


def test_markdown_inline_runs():
    from transdoc.regenerate.markdown import render
    md = render(_mixed_block(), Config(target_lang="id"))
    assert "**API**" in md and "<sup>" in md and "see " in md


def test_docx_inline_runs(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.regenerate.docx_out import render
    out = tmp_path / "r.docx"
    render(_mixed_block(), Config(target_lang="id"), str(out))
    p = next(p for p in docx.Document(str(out)).paragraphs if p.text.strip())
    assert any(r.font.bold and r.text == "API" for r in p.runs)
    assert any(r.font.superscript for r in p.runs)


def test_uniform_docx_has_no_runs(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    dd = docx.Document()
    dd.add_paragraph("a plain uniform paragraph with no inline styling at all")
    p = tmp_path / "u.docx"
    dd.save(str(p))
    doc = extract(str(p), Config(target_lang="id"))
    para = next(b for b in doc.blocks if b.type == BlockType.PARAGRAPH)
    assert para.runs == []     # uniform -> no runs -> block-level path unchanged


def test_docx_extract_captures_mixed_runs(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    dd = docx.Document()
    para = dd.add_paragraph("normal ")
    para.add_run("BOLD").bold = True
    para.add_run(" tail")
    p = tmp_path / "m.docx"
    dd.save(str(p))
    doc = extract(str(p), Config(target_lang="id"))
    blk = next(b for b in doc.blocks if b.type == BlockType.PARAGRAPH)
    assert len(blk.runs) >= 2
    assert any(r.style.bold and r.text == "BOLD" for r in blk.runs)
