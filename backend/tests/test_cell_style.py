# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Table cell font size + span render (audit P2: pdf-flow hardcoded 8pt; spans ignored)."""

from __future__ import annotations

from transdoc.ir import Cell
from transdoc.regenerate.pdf_out import _cell_td, _table_html


def test_cell_td_uses_size_and_span():
    td = _cell_td(Cell(text="hi", size=14.0, bold=True, colspan=2))
    assert "font-size:14pt" in td and "font-weight:bold" in td and 'colspan="2"' in td


def test_cell_td_defaults_8pt():
    assert "font-size:8pt" in _cell_td(Cell(text="x"))


def test_table_html_rows():
    html = _table_html([[Cell(text="A", size=10.0), Cell(text="B")]])
    assert html.count("<td") == 2 and "<table" in html and "A" in html and "B" in html
