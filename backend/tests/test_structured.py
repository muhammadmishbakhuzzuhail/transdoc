# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Structured PDF extraction (PP-StructureV3 path): regions -> IR with formulas as LaTeX,
text from the digital layer, figures/tables as crops. Uses a fake extractor — no paddle."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config  # noqa: E402
from transdoc.extract.structured import extract_structured  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402
from transdoc.layout.structure import StructRegion  # noqa: E402


class _FakeExtractor:
    def extract_pages(self, fdoc, pnos):
        return {0: [
            StructRegion("paragraph_title", 40, 40, 300, 60, "", 0),
            StructRegion("text", 40, 80, 500, 120, "ocr fallback text", 1),
            StructRegion("formula", 40, 140, 300, 170, r"\frac{1}{2}\sqrt{d_k}", 2),
            StructRegion("image", 40, 200, 300, 360, "", 3),
            StructRegion("footer", 40, 760, 200, 775, "page 1", 4),  # furniture -> skipped
        ]}


def _pdf(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((42, 55), "Real Heading From Digital Layer")
    p.insert_text((42, 95), "Body paragraph from the digital text layer.")
    path = tmp_path / "x.pdf"
    d.save(str(path))
    d.close()
    return str(path)


def test_structured_builds_ir(monkeypatch, tmp_path):
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _FakeExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))

    by_type = {}
    for b in doc.blocks:
        by_type.setdefault(b.type, []).append(b)

    # formula kept as raw LaTeX, never translated
    formulas = by_type[BlockType.FORMULA]
    assert len(formulas) == 1 and formulas[0].text == r"\frac{1}{2}\sqrt{d_k}"

    # text region picked up the DIGITAL layer text, not the OCR fallback
    paras = by_type[BlockType.PARAGRAPH]
    assert any("digital text layer" in b.text for b in paras)
    assert not any(b.text == "ocr fallback text" for b in doc.blocks)

    # image -> verbatim crop with an image file
    figs = by_type[BlockType.FIGURE]
    assert len(figs) == 1 and figs[0].crop_region and figs[0].image_path

    # footer furniture dropped; blocks are in reading order
    assert all("page 1" not in (b.text or "") for b in doc.blocks)
    assert [b.reading_order for b in doc.blocks] == sorted(b.reading_order for b in doc.blocks)


class _TableExtractor:
    def extract_pages(self, fdoc, pnos):
        html = "<table><tr><td>Name</td><td colspan='2'>Value</td></tr>" \
               "<tr><td>a</td><td>1</td><td>2</td></tr></table>"
        return {0: [StructRegion("table", 40, 40, 500, 200, html, 0)]}


def test_table_html_parsed_to_cells(monkeypatch, tmp_path):
    pytest.importorskip("bs4")
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _TableExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    tables = [b for b in doc.blocks if b.type == BlockType.TABLE]
    assert len(tables) == 1
    rows = tables[0].table.rows
    assert [c.text for c in rows[0]] == ["Name", "Value"]
    assert rows[0][1].colspan == 2
    assert [c.text for c in rows[1]] == ["a", "1", "2"]


def test_parse_table_header_span_nested():
    pytest.importorskip("bs4")
    from transdoc.extract.structured import _parse_table_html

    # <th> first row -> header + bold; colspan preserved
    t = _parse_table_html(
        "<table><tr><th>Name</th><th>Val</th></tr><tr><td colspan=2>merged</td></tr></table>")
    assert t.has_header_row is True
    assert all(c.bold for c in t.rows[0])
    assert t.rows[1][0].colspan == 2

    # nested <table> inside a cell -> Cell.table populated, NOT flattened, rows not double-counted
    n = _parse_table_html(
        "<table><tr><td>outer</td>"
        "<td><table><tr><td>i1</td><td>i2</td></tr></table></td></tr></table>")
    assert len(n.rows) == 1 and len(n.rows[0]) == 2          # outer not inflated by inner row
    assert n.rows[0][1].table is not None
    assert len(n.rows[0][1].table.rows[0]) == 2

    # plain table (no <th>) -> header flag is False (was hard-coded True before)
    p = _parse_table_html("<table><tr><td>a</td><td>b</td></tr></table>")
    assert p.has_header_row is False


def test_padded_crop_expands_and_clamps():
    from transdoc.extract.structured import _CROP_PAD, _padded

    class _Box:
        x0 = y0 = 0
        x1 = y1 = 0

    page = fitz.open()
    pg = page.new_page(width=200, height=200)
    # interior region -> padded on every side
    r = _Box()
    r.x0, r.y0, r.x1, r.y1 = 50, 50, 100, 100
    p = _padded(r, pg)
    assert p.x0 == 50 - _CROP_PAD and p.x1 == 100 + _CROP_PAD
    # edge region -> clamped to the page, never negative / off-page
    e = _Box()
    e.x0, e.y0, e.x1, e.y1 = 0, 0, 200, 200
    pe = _padded(e, pg)
    assert pe.x0 == 0 and pe.y0 == 0 and pe.x1 == 200 and pe.y1 == 200
    page.close()


def test_pick_text_falls_back_when_digital_is_garbage():
    from transdoc.extract.structured import _pick_text

    # clean digital layer wins
    assert _pick_text("Real clean paragraph long enough to judge", "ocr") == (
        "Real clean paragraph long enough to judge", True)
    # CID/subset garbage digital -> use the OCR content instead (audit P9)
    text, ok = _pick_text("GLYPH<c=1>" * 5, "clean OCR fallback")
    assert text == "clean OCR fallback" and ok is False
    # empty digital -> OCR content
    assert _pick_text("", "ocr only") == ("ocr only", False)
    # inline-math content preferred over the flattened digital layer
    _, ok = _pick_text("flattened dk", "value $d_k$ holds")
    assert ok is False


class _InlineMathExtractor:
    def extract_pages(self, fdoc, pnos):
        # bbox in an empty area (no digital text there) so we test content selection
        return {0: [
            StructRegion("text", 40, 400, 500, 440, r"for small values of $d_{k}$ it holds", 0),
        ]}


def test_inline_math_uses_latex_content(monkeypatch, tmp_path):
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _InlineMathExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    paras = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH]
    assert any("$d_{k}$" in b.text for b in paras)   # inline LaTeX kept, not flattened


class _DupExtractor:
    def extract_pages(self, fdoc, pnos):
        full = "This is the full sentence about scaled dot product attention indeed"
        return {0: [
            StructRegion("text", 40, 300, 500, 330, "the full sentence about scaled dot", 0),
            StructRegion("text", 41, 301, 501, 331, full, 1),   # overlapping, longer
        ]}


def test_dedup_keeps_longer_overlapping(monkeypatch, tmp_path):
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _DupExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    paras = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH]
    assert len(paras) == 1
    assert "full sentence about scaled dot product attention indeed" in paras[0].text


def test_region_style_reads_dominant_font_size_weight(tmp_path):
    """The structured path enriches each text block with the dominant font/size/weight of the
    digital spans in its region, instead of an empty Style."""
    from transdoc.extract.structured import _region_style

    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((50, 100), "Big Bold Heading", fontsize=20, fontname="hebo")  # Helvetica-Bold
    p.insert_text((50, 300), "small body text here", fontsize=9, fontname="helv")
    path = tmp_path / "styled.pdf"
    d.save(str(path))
    d.close()

    pg = fitz.open(str(path))[0]
    head = _region_style(pg, fitz.Rect(40, 85, 400, 115))
    body = _region_style(pg, fitz.Rect(40, 288, 400, 312))
    assert round(head.size) == 20 and head.bold is True
    assert round(body.size) == 9 and body.bold is False


def test_reading_order_sinks_footnote_with_order_zero():
    """PP-StructureV3 hands footnotes block_order=0 (a floating element it can't place), which
    naively sorts them to the top. _ordered_regions must keep the body in order and push the
    footnote to the end."""
    from transdoc.extract.structured import _ordered_regions

    regs = [
        StructRegion("footnote", 40, 620, 500, 640, "* equal contribution", 0),  # order 0
        StructRegion("doc_title", 40, 47, 500, 70, "Title", 1),
        StructRegion("text", 40, 145, 500, 200, "body", 2),
        StructRegion("abstract", 40, 230, 500, 400, "abstract", 3),
    ]
    order = [r.label for r in _ordered_regions(regs)]
    assert order == ["doc_title", "text", "abstract", "footnote"]   # footnote last, not first


def test_reading_order_falls_back_to_position_without_orders():
    from transdoc.extract.structured import _ordered_regions

    regs = [
        StructRegion("text", 40, 300, 500, 340, "lower", 0),
        StructRegion("text", 40, 100, 500, 140, "upper", 0),
    ]
    # no positive orders anywhere -> pure top-to-bottom by y0
    assert [r.y0 for r in _ordered_regions(regs)] == [100, 300]


def test_clean_latex_collapses_letter_spacing():
    from transdoc.extract.structured import _clean_latex
    assert _clean_latex(r"\operatorname{A t t e n t i o n}") == r"\operatorname{Attention}"
    assert _clean_latex(r"\frac{Q K^{T}}{\sqrt{d_{k}}}") == r"\frac{QK^{T}}{\sqrt{d_{k}}}"


class _SpacedFormulaExtractor:
    def extract_pages(self, fdoc, pnos):
        return {0: [
            StructRegion("formula", 40, 140, 300, 170, r"\operatorname{s o f t m a x}(x)", 0),
            StructRegion("text", 40, 400, 500, 440, r"with $d_{k}$ kept and prose left alone", 1),
        ]}


def test_formula_and_inline_latex_cleaned(monkeypatch, tmp_path):
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _SpacedFormulaExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    f = next(b for b in doc.blocks if b.type == BlockType.FORMULA)
    assert f.text == r"\operatorname{softmax}(x)"
    p = next(b for b in doc.blocks if b.type == BlockType.PARAGRAPH)
    assert "$d_{k}$" in p.text and "prose left alone" in p.text   # prose words untouched


class _PdfMixExtractor:
    def extract_pages(self, fdoc, pnos):
        html = "<table><tr><td>Name</td><td>Value</td></tr><tr><td>a</td><td>1</td></tr></table>"
        return {0: [
            StructRegion("paragraph_title", 40, 40, 300, 60, "", 0),
            StructRegion("text", 40, 80, 500, 120, "", 1),       # uses digital layer
            StructRegion("formula", 40, 140, 300, 170, r"\frac{a}{b}", 2),
            StructRegion("table", 40, 200, 500, 320, html, 3),
            StructRegion("image", 40, 360, 300, 500, "", 4),
        ]}


def test_structured_ir_renders_to_pdf_reconstruct(monkeypatch, tmp_path):
    """PDF->PDF: structured IR (formula crop + real table grid + figure crop + text) flows
    through render_reconstruct into a valid PDF that keeps the source page geometry."""
    from transdoc.config import OutputFormat
    from transdoc.regenerate.pdf_out import render_reconstruct

    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda *a, **k: _PdfMixExtractor())
    src = _pdf(tmp_path)
    doc = extract_structured(src, Config(target_lang="id", layout="paddle"))
    # echo "translation": leave output_text == source (no translator in this test)
    out = tmp_path / "out.pdf"
    render_reconstruct(doc, Config(target_lang="id", layout="paddle",
                                   output_format=OutputFormat.PDF), str(out))

    rendered = fitz.open(str(out))
    assert rendered.page_count == 1
    assert (round(rendered[0].rect.width), round(rendered[0].rect.height)) == (595, 842)
    txt = rendered[0].get_text()
    assert "Name" in txt and "Value" in txt          # table grid rebuilt as real cells
    assert sum(len(p.get_images()) for p in rendered) >= 1   # formula/figure crop placed


def test_markdown_renders_formula_as_display_math():
    from transdoc.ir import BBox, Block, Confidence, Document
    from transdoc.regenerate.markdown import render

    doc = Document(source_path="x", mime="application/pdf")
    doc.blocks = [Block(id="f", type=BlockType.FORMULA, text=r"\frac{a}{b}",
                        bbox=BBox(x0=0, y0=0, x1=1, y1=1), confidence=Confidence())]
    md = render(doc, Config(target_lang="id"))
    assert "$$" in md and r"\frac{a}{b}" in md
