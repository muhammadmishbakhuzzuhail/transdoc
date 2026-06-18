"""Form detection: an interactive AcroForm (field widgets) is a form (must be overlaid, not
rebuilt). Vector strokes alone are NOT a form — figures, bordered tables and scans have strokes too
and were wrongly forced into the overflow-prone overlay renderer."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.ingest.detect import is_form_pdf  # noqa: E402


def test_acroform_with_widget_is_a_form(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((40, 40), "Application form")
    w = fitz.Widget()
    w.field_name = "name"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(40, 80, 300, 100)
    p.add_widget(w)
    path = tmp_path / "form.pdf"
    d.save(str(path))
    d.close()
    assert is_form_pdf(str(path)) is True


def test_stroke_heavy_but_no_widget_is_not_a_form(tmp_path):
    # 30 ruled lines (like a figure/table or a flat scan) must NOT be treated as a form — this is
    # the false-positive that pushed arXiv/Wikipedia/scans into the overlay renderer.
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((40, 40), "Figure 1")
    for i in range(30):
        y = 80 + i * 20
        p.draw_line(fitz.Point(40, y), fitz.Point(540, y))
    path = tmp_path / "lines.pdf"
    d.save(str(path))
    d.close()
    assert is_form_pdf(str(path)) is False


def test_prose_pdf_is_not_a_form(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_textbox(fitz.Rect(40, 40, 555, 800),
                     "A normal article paragraph with flowing prose. " * 40, fontsize=11)
    path = tmp_path / "prose.pdf"
    d.save(str(path))
    d.close()
    assert is_form_pdf(str(path)) is False
