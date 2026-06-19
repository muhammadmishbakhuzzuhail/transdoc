# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""DOCX section header/footer content: captured (body walk misses it), translated, and
re-emitted into the output section's header/footer."""

from __future__ import annotations

import pytest

from transdoc.config import Config

docx = pytest.importorskip("docx")


def test_capture_header_footer(tmp_path):
    from transdoc.extract.docx import extract
    dd = docx.Document()
    dd.add_paragraph("body text")
    sec = dd.sections[0]
    sec.header.paragraphs[0].text = "Confidential — Q3 report"
    sec.footer.paragraphs[0].text = "Page footer note"
    f = tmp_path / "in.docx"
    dd.save(str(f))
    doc = extract(str(f), Config(target_lang="id"))
    assert [b.text for b in doc.headers] == ["Confidential — Q3 report"]
    assert [b.text for b in doc.footers] == ["Page footer note"]
    # header/footer stay OFF the body block list
    assert all("Confidential" not in b.text for b in doc.blocks)


def test_header_footer_translate_collected():
    from transdoc.ir import Block, BlockType, Document
    from transdoc.translate.base import translate_document

    class Echo:
        name = "echo"
        cacheable = False

        def translate_batch(self, texts, cfg, src=None):
            return [t + " [id]" for t in texts]

    d = Document(source_path="x", mime="docx")
    d.blocks = [Block(id="a", type=BlockType.PARAGRAPH, text="body")]
    d.headers = [Block(id="h", type=BlockType.HEADER, text="head")]
    d.footers = [Block(id="f", type=BlockType.FOOTER, text="foot")]
    translate_document(d, Echo(), Config(target_lang="id"))
    assert d.headers[0].translated == "head [id]"
    assert d.footers[0].translated == "foot [id]"


def test_render_writes_header_footer(tmp_path):
    from transdoc.ir import Block, BlockType, Confidence, Document
    from transdoc.regenerate.docx_out import render
    d = Document(source_path="x", mime="docx")
    d.blocks = [Block(id="a", type=BlockType.PARAGRAPH, text="body",
                      confidence=Confidence())]
    d.headers = [Block(id="h", type=BlockType.HEADER, text="head", translated="kepala")]
    d.footers = [Block(id="f", type=BlockType.FOOTER, text="foot", translated="kaki")]
    out = tmp_path / "o.docx"
    render(d, Config(target_lang="id"), str(out))
    sec = docx.Document(str(out)).sections[0]
    assert "kepala" in sec.header.paragraphs[0].text
    assert "kaki" in sec.footer.paragraphs[0].text
