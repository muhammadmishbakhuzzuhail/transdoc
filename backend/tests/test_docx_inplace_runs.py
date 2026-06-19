# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""In-place DOCX keeps intra-paragraph run styling (a bold word) on translation, instead of
flattening the whole paragraph to run-0."""

from __future__ import annotations

import pytest

from transdoc.config import Config

docx = pytest.importorskip("docx")


def test_inplace_preserves_bold_word(tmp_path):
    from transdoc.extract.docx import extract
    from transdoc.regenerate.docx_inplace import render

    dd = docx.Document()
    p = dd.add_paragraph()
    p.add_run("plain start ")
    p.add_run("BOLD").bold = True
    p.add_run(" plain end")
    src = tmp_path / "in.docx"
    dd.save(str(src))

    doc = extract(str(src), Config(target_lang="id"))
    blk = next(b for b in doc.blocks if "BOLD" in b.text)
    assert blk.runs, "mixed-style paragraph should have inline runs captured"
    for r in blk.runs:                          # fake a translation per run
        r.translated = r.text.lower() + "X"

    out = tmp_path / "out.docx"
    render(doc, Config(target_lang="id"), str(out))
    op = docx.Document(str(out)).paragraphs[0]
    bolds = [r.text for r in op.runs if r.bold]
    assert any("bold" in t.lower() for t in bolds)   # the bold word stayed bold (not flattened)


def test_inplace_uniform_paragraph_still_works(tmp_path):
    from transdoc.extract.docx import extract
    from transdoc.regenerate.docx_inplace import render
    dd = docx.Document()
    dd.add_paragraph("a uniform paragraph here")
    src = tmp_path / "u.docx"
    dd.save(str(src))
    doc = extract(str(src), Config(target_lang="id"))
    doc.blocks[0].translated = "paragraf seragam di sini"
    out = tmp_path / "uo.docx"
    render(doc, Config(target_lang="id"), str(out))
    assert "paragraf seragam" in docx.Document(str(out)).paragraphs[0].text
