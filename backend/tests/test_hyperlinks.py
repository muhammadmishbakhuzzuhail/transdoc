# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Hyperlinks captured from PDF + rendered to markdown / docx / pdf (audit P1, end-to-end)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style


def _linked_doc():
    d = Document(source_path="x", mime="application/pdf")
    bb = BBox(x0=0, y0=0, x1=200, y1=20)
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="visit our site", bbox=bb,
                      confidence=Confidence(), style=Style(link="https://example.com"))]
    return d


def test_markdown_renders_link():
    from transdoc.regenerate.markdown import render
    md = render(_linked_doc(), Config(target_lang="id"))
    assert "[visit our site](https://example.com)" in md


def test_docx_renders_hyperlink(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.regenerate.docx_out import render
    out = tmp_path / "l.docx"
    render(_linked_doc(), Config(target_lang="id"), str(out))
    d = docx.Document(str(out))
    # hyperlink relationship present + the link text carried
    rels = d.part.rels
    assert any("example.com" in (r.target_ref or "") for r in rels.values())
    assert any(p.hyperlinks and p.hyperlinks[0].address == "https://example.com"
               for p in d.paragraphs)


def test_pdf_capture_attaches_link(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.links import attach_pdf_links

    src = d = fitz.open()
    p = d.new_page(width=400, height=400)
    p.insert_text((50, 50), "click here")
    p.insert_link({"kind": fitz.LINK_URI, "from": fitz.Rect(48, 40, 140, 56),
                   "uri": "https://t.example"})
    path = tmp_path / "linked.pdf"
    d.save(str(path))
    d.close()
    # reopen from disk — links persist after save (in-memory get_links is empty)
    src = fitz.open(str(path))
    blocks = [Block(id="b", type=BlockType.PARAGRAPH, text="click here",
                    bbox=BBox(x0=46, y0=38, x1=150, y1=58), confidence=Confidence(),
                    style=Style())]
    attach_pdf_links(src[0], blocks)
    src.close()
    assert blocks[0].style.link == "https://t.example"
