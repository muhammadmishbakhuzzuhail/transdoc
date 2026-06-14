"""Vector line-art capture + redraw: reconstruct keeps rules/dividers/boxes it used to drop."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.extract.vectors import capture  # noqa: E402
from transdoc.regenerate.pdf_out import _redraw_vectors  # noqa: E402


def _pdf_with_shapes(tmp_path):
    d = fitz.open()
    p = d.new_page(width=400, height=400)
    p.draw_line(fitz.Point(40, 50), fitz.Point(360, 50), color=(0, 0, 0), width=1.0)
    p.draw_rect(fitz.Rect(40, 80, 360, 200), color=(0, 0, 1), width=0.8)
    path = tmp_path / "shapes.pdf"
    d.save(str(path))
    d.close()
    return str(path)


def test_capture_lines_and_rects(tmp_path):
    d = fitz.open(_pdf_with_shapes(tmp_path))
    v = capture(d[0])
    d.close()
    kinds = {x["kind"] for x in v}
    assert "line" in kinds and "rect" in kinds


def test_capture_skips_full_page_background(tmp_path):
    d = fitz.open()
    p = d.new_page(width=400, height=400)
    p.draw_rect(fitz.Rect(0, 0, 400, 400), fill=(0.9, 0.9, 0.9))  # full-page bg panel
    p.draw_line(fitz.Point(10, 200), fitz.Point(390, 200), color=(0, 0, 0))
    path = tmp_path / "bg.pdf"
    d.save(str(path))
    v = capture(d[0])
    d.close()
    # the full-page rect is dropped (background), the line is kept
    assert all(x["kind"] != "rect" for x in v)
    assert any(x["kind"] == "line" for x in v)


def test_redraw_round_trips(tmp_path):
    d = fitz.open(_pdf_with_shapes(tmp_path))
    v = capture(d[0])
    d.close()
    out = fitz.open()
    pg = out.new_page(width=400, height=400)
    _redraw_vectors(pg, v)
    assert len(pg.get_drawings()) == len(v) and len(v) >= 2
    out.close()
