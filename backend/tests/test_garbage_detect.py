# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""CID/ToUnicode garbage + text-as-geometry detection -> OCR routing (research E)."""

from __future__ import annotations

import pytest

from transdoc.extract.pdf import _looks_garbage


def test_clean_text_not_garbage():
    assert _looks_garbage("This is a perfectly normal sentence in English here.") is False
    assert _looks_garbage("文中包含中文字符也属于正常文本不应判为乱码内容") is False


def test_glyph_placeholder_is_garbage():
    assert _looks_garbage("GLYPH<c=3,font=ABCDEE+Arial> GLYPH<c=4> some more text here") is True


def test_replacement_char_ratio_is_garbage():
    assert _looks_garbage("��� ��� ��� ��� ��� ��� ��� ���") is True


def test_text_as_geometry(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.pdf import _text_as_geometry

    # a page with many vector paths but almost no text -> glyphs drawn as outlines
    d = fitz.open()
    p = d.new_page(width=400, height=400)
    for i in range(2100):
        y = (i % 380) + 5
        p.draw_line(fitz.Point(5, y), fitz.Point(7, y))
    assert _text_as_geometry(p) is True

    # a normal text page -> not geometry
    d2 = fitz.open()
    p2 = d2.new_page(width=400, height=400)
    p2.insert_textbox(fitz.Rect(20, 20, 380, 380), "Real text content. " * 20, fontsize=11)
    assert _text_as_geometry(p2) is False
    d.close()
    d2.close()
