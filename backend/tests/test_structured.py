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
                        lambda: _FakeExtractor())
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
                        lambda: _TableExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    tables = [b for b in doc.blocks if b.type == BlockType.TABLE]
    assert len(tables) == 1
    rows = tables[0].table.rows
    assert [c.text for c in rows[0]] == ["Name", "Value"]
    assert rows[0][1].colspan == 2
    assert [c.text for c in rows[1]] == ["a", "1", "2"]


class _InlineMathExtractor:
    def extract_pages(self, fdoc, pnos):
        # bbox in an empty area (no digital text there) so we test content selection
        return {0: [
            StructRegion("text", 40, 400, 500, 440, r"for small values of $d_{k}$ it holds", 0),
        ]}


def test_inline_math_uses_latex_content(monkeypatch, tmp_path):
    monkeypatch.setattr("transdoc.layout.structure.get_structure_extractor",
                        lambda: _InlineMathExtractor())
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
                        lambda: _DupExtractor())
    doc = extract_structured(_pdf(tmp_path), Config(target_lang="id", layout="paddle"))
    paras = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH]
    assert len(paras) == 1
    assert "full sentence about scaled dot product attention indeed" in paras[0].text


def test_markdown_renders_formula_as_display_math():
    from transdoc.ir import BBox, Block, Confidence, Document
    from transdoc.regenerate.markdown import render

    doc = Document(source_path="x", mime="application/pdf")
    doc.blocks = [Block(id="f", type=BlockType.FORMULA, text=r"\frac{a}{b}",
                        bbox=BBox(x0=0, y0=0, x1=1, y1=1), confidence=Confidence())]
    md = render(doc, Config(target_lang="id"))
    assert "$$" in md and r"\frac{a}{b}" in md
