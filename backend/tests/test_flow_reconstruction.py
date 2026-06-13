"""Deeper FLOW reconstruction: embedded images are reflowed back, list items are grouped in
a <ul>, and block-level styling (bold/colour/align) is carried into the output."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style  # noqa: E402
from transdoc.pipeline import run  # noqa: E402
from transdoc.regenerate.pdf_out import _flow_style, render_flow  # noqa: E402


def test_image_is_reflowed_back(tmp_path):
    src = tmp_path / "fig.pdf"
    d = fitz.open()
    pg = d.new_page(width=400, height=500)
    pg.insert_text((40, 40), "Heading on the page here", fontsize=18)
    pg.insert_text((40, 80), "Some body text to translate goes here on the page.", fontsize=11)
    logo = fitz.open()
    logo.new_page(width=80, height=80).draw_rect(fitz.Rect(0, 0, 80, 80), fill=(0, 0.4, 1))
    pg.insert_image(fitz.Rect(40, 120, 200, 280), pixmap=logo[0].get_pixmap())
    d.save(str(src))

    out = tmp_path / "o.pdf"
    r = run(str(src), Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                             output_format=OutputFormat.PDF, fidelity=Fidelity.FLOW,
                             mode=Mode.FULL), out_path=str(out))
    assert any(b.type == BlockType.FIGURE for b in r.doc.blocks)
    assert sum(len(p.get_images()) for p in fitz.open(str(out))) >= 1   # image survived reflow


def test_block_style_css():
    b = Block(id="x", type=BlockType.PARAGRAPH, page=0, text="t",
              style=Style(bold=True, color="#cc0000", align="center"),
              confidence=Confidence(source="digital"))
    css = _flow_style(b)
    assert "font-weight:bold" in css and "color:#cc0000" in css and "text-align:center" in css


def test_list_items_grouped(tmp_path):
    doc = Document(source_path="x.pdf", mime="application/pdf")
    for i in range(3):
        blk = Block(id=f"l{i}", type=BlockType.LIST_ITEM, page=0, text=f"item {i}",
                    bbox=BBox(x0=0, y0=i, x1=10, y1=i + 1), confidence=Confidence(source="digital"))
        blk.translated = f"butir {i}"
        doc.blocks.append(blk)
    out = tmp_path / "o.pdf"
    render_flow(doc, Config(target_lang="id"), str(out))      # must not crash; groups <ul>
    assert fitz.open(str(out)).page_count >= 1


def test_flow_preserves_font_size_hierarchy():
    from transdoc.ir import Block, BlockType, Confidence, Style
    title = Block(id="t", type=BlockType.TITLE, page=0, text="T",
                  style=Style(size=20.0), confidence=Confidence(source="digital"))
    body = Block(id="b", type=BlockType.PARAGRAPH, page=0, text="b",
                 style=Style(size=11.0), confidence=Confidence(source="digital"))
    assert "font-size:20.0pt" in _flow_style(title)
    assert "font-size:11.0pt" in _flow_style(body)


def test_flow_no_size_omits_font_size():
    from transdoc.ir import Block, BlockType, Confidence, Style
    b = Block(id="x", type=BlockType.PARAGRAPH, page=0, text="x",
              style=Style(), confidence=Confidence(source="digital"))
    assert "font-size" not in _flow_style(b)
