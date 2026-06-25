# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Dashed vector strokes: dash pattern captured and re-applied in reconstruct."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")


def test_capture_dash_pattern(tmp_path):
    from transdoc.extract.vectors import capture
    d = fitz.open()
    p = d.new_page(width=300, height=300)
    p.draw_line(fitz.Point(20, 20), fitz.Point(280, 20), dashes="[3 2] 0", width=1)
    f = tmp_path / "d.pdf"
    d.save(str(f))
    d.close()
    src = fitz.open(str(f))
    lines = [v for v in capture(src[0]) if v["kind"] == "line"]
    src.close()
    assert lines and lines[0].get("dashes")          # dash pattern carried, not dropped


def test_solid_line_no_dashes(tmp_path):
    from transdoc.extract.vectors import capture
    d = fitz.open()
    p = d.new_page(width=300, height=300)
    p.draw_line(fitz.Point(20, 20), fitz.Point(280, 20), width=1)
    f = tmp_path / "s.pdf"
    d.save(str(f))
    d.close()
    src = fitz.open(str(f))
    lines = [v for v in capture(src[0]) if v["kind"] == "line"]
    src.close()
    assert lines and not lines[0].get("dashes")      # solid -> no dash pattern


def test_redraw_accepts_dashes():
    from transdoc.regenerate.pdf_out import _redraw_vectors
    out = fitz.open()
    page = out.new_page(width=300, height=300)
    _redraw_vectors(page, [{"kind": "line", "x0": 10, "y0": 10, "x1": 290, "y1": 10,
                            "color": "#000000", "width": 1, "dashes": "[3 2] 0"}])
    assert page.get_drawings()                        # drawn without error
    out.close()
