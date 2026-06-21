# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""A clean single-column, image-free digital PDF skips the slow PP-StructureV3 path (paddle
cold-load ~30s) for the fast heuristic extractor; any image or multi-column page keeps structured."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.extract import _is_simple_digital_pdf  # noqa: E402


def _single_col(path):
    d = fitz.open()
    pg = d.new_page(width=595, height=842)
    pg.insert_textbox(fitz.Rect(60, 60, 535, 800),
                      ("A single column of ordinary body text. " * 30), fontsize=11)
    d.save(str(path))
    d.close()


def _two_col(path):
    d = fitz.open()
    pg = d.new_page(width=595, height=842)
    para = "Column body text that fills several lines of a paragraph block here. " * 3
    # several stacked paragraph blocks per column (a real multi-column page has many blocks; one
    # textbox per column collapses to a single block and won't read as side-by-side)
    for y in (60, 200, 340, 480):
        pg.insert_textbox(fitz.Rect(60, y, 290, y + 120), para, fontsize=10)
        pg.insert_textbox(fitz.Rect(305, y, 535, y + 120), para, fontsize=10)
    d.save(str(path))
    d.close()


def test_single_column_no_image_is_simple(tmp_path):
    p = tmp_path / "s.pdf"
    _single_col(p)
    assert _is_simple_digital_pdf(str(p)) is True


def test_two_column_is_not_simple(tmp_path):
    p = tmp_path / "t.pdf"
    _two_col(p)
    assert _is_simple_digital_pdf(str(p)) is False


def test_page_with_image_is_not_simple(tmp_path):
    from PIL import Image
    img = tmp_path / "i.png"
    Image.new("RGB", (200, 120), (200, 210, 240)).save(img)
    d = fitz.open()
    pg = d.new_page(width=595, height=842)
    pg.insert_textbox(fitz.Rect(60, 60, 535, 400), "A single column of text. " * 30, fontsize=11)
    pg.insert_image(fitz.Rect(100, 450, 400, 600), filename=str(img))
    out = tmp_path / "wi.pdf"
    d.save(str(out))
    d.close()
    assert _is_simple_digital_pdf(str(out)) is False


def test_env_override_disables_skip(tmp_path, monkeypatch):
    p = tmp_path / "s.pdf"
    _single_col(p)
    monkeypatch.setenv("TRANSDOC_SIMPLE_SKIP_DISABLE", "1")
    assert _is_simple_digital_pdf(str(p)) is False
