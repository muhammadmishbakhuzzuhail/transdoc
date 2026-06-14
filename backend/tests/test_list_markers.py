"""Ordered-vs-bullet list markers + nesting level round-trip (audit P2)."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style


def _li(text, ordered, level):
    return Block(id=text, type=BlockType.LIST_ITEM, text=text,
                 bbox=BBox(x0=0, y0=0, x1=1, y1=1), confidence=Confidence(),
                 style=Style(list_ordered=ordered, list_level=level))


def test_markdown_ordered_vs_bullet_and_indent():
    from transdoc.regenerate.markdown import render
    d = Document(source_path="x", mime="application/pdf")
    d.blocks = [_li("first", True, 0), _li("nested", False, 1)]
    md = render(d, Config(target_lang="id"))
    assert "1. first" in md
    assert "  - nested" in md          # level 1 -> 2-space indent, bullet


def test_docx_extract_detects_numbered_list(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    dd = docx.Document()
    dd.add_paragraph("step one", style="List Number")
    dd.add_paragraph("a bullet", style="List Bullet")
    p = tmp_path / "l.docx"
    dd.save(str(p))
    doc = extract(str(p), Config(target_lang="id"))
    lis = [b for b in doc.blocks if b.type == BlockType.LIST_ITEM]
    assert any(b.style.list_ordered for b in lis)        # numbered detected
    assert any(not b.style.list_ordered for b in lis)    # bullet detected
