"""Form detection: a PDF page that is a grid of vector field-lines/boxes is a form (must be
overlaid, not rebuilt), while a prose page is not."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.ingest.detect import is_form_pdf  # noqa: E402


def test_form_pdf_with_many_strokes(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((40, 40), "Application form")
    for i in range(30):                       # 30 field underlines -> clearly a form
        y = 80 + i * 20
        p.draw_line(fitz.Point(40, y), fitz.Point(540, y))
    path = tmp_path / "form.pdf"
    d.save(str(path))
    d.close()
    assert is_form_pdf(str(path)) is True


def test_prose_pdf_is_not_a_form(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_textbox(fitz.Rect(40, 40, 555, 800),
                     "A normal article paragraph with flowing prose. " * 40, fontsize=11)
    path = tmp_path / "prose.pdf"
    d.save(str(path))
    d.close()
    assert is_form_pdf(str(path)) is False
