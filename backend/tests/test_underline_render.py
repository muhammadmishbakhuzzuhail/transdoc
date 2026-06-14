"""Underline renders in markdown + pdf (captured in DOCX extract + docx_out already)."""

from __future__ import annotations


from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style


def _doc():
    d = Document(source_path="x", mime="application/pdf")
    d.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="underlined text",
                      bbox=BBox(x0=0, y0=0, x1=200, y1=20), confidence=Confidence(),
                      style=Style(underline=True))]
    return d


def test_markdown_underline():
    from transdoc.regenerate.markdown import render
    assert "<u>underlined text</u>" in render(_doc(), Config(target_lang="id"))


def test_pdf_block_html_underline():
    from transdoc.regenerate.pdf_out import _block_html
    html, _ = _block_html(_doc().blocks[0])
    assert "text-decoration:underline" in html
