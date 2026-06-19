# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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


def test_restore_edge_ws_keeps_run_boundaries():
    from transdoc.translate.base import _restore_edge_ws
    # engine strips edge whitespace; we re-apply the source run's so adjacent runs don't glue
    assert _restore_edge_ws("international ", "internasional") == "internasional "
    assert _restore_edge_ws(" now", "sekarang") == " sekarang"
    # a styled mid-word fragment (no edge space) stays glued
    assert _restore_edge_ws("Wiki", "Wiki") == "Wiki"
    assert _restore_edge_ws("pedia", "pedia") == "pedia"


def test_translated_runs_dont_merge():
    # per-run translation strips trailing spaces; the fix keeps a boundary space between runs so
    # concatenated output reads "... internasional Deklarasi" not "...internasionalDeklarasi".
    from transdoc.config import Engine
    from transdoc.translate import get_translator, translate_document
    d = Document(source_path="x", mime="docx")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    b = Block(id="1", type=BlockType.PARAGRAPH, text="international Declaration", bbox=bb,
              confidence=Confidence(), runs=[
                  Run(text="international ", style=Style()),
                  Run(text="Declaration", style=Style(bold=True))])
    d.blocks = [b]
    cfg = Config(target_lang="id", engine=Engine.ECHO)
    translate_document(d, get_translator(cfg), cfg)
    joined = "".join(r.output_text for r in b.runs)
    assert joined.count(" ") >= 1 and "  " not in joined   # boundary space survived, not doubled


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
