# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""TEDS-Struct table-structure metric + eval_table sidecar parsing."""

from __future__ import annotations

import pytest

pytest.importorskip("bs4")

from transdoc.eval.metrics import table_teds  # noqa: E402
from transdoc.ir import Cell, Table  # noqa: E402


def _grid():
    return Table(rows=[[Cell(text="a"), Cell(text="b")], [Cell(text="c"), Cell(text="d")]])


def test_identical_structure_scores_one():
    html = "<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr></table>"
    assert table_teds(html, _grid()) == 1.0


def test_text_differences_ignored():
    # TEDS-Struct scores the grid, not the words — different cell text, same shape -> 1.0
    html = "<table><tr><td>X</td><td>Y</td></tr><tr><td>Z</td><td>W</td></tr></table>"
    assert table_teds(html, _grid()) == 1.0


def test_missing_cell_penalised():
    html = "<table><tr><td>a</td></tr><tr><td>c</td><td>d</td></tr></table>"
    assert table_teds(html, _grid()) < 1.0


def test_wrong_span_penalised():
    html = "<table><tr><td colspan=2>a</td></tr><tr><td>c</td><td>d</td></tr></table>"
    assert table_teds(html, _grid()) < 1.0


def test_extra_row_penalised():
    html = ("<table><tr><td>a</td><td>b</td></tr><tr><td>c</td><td>d</td></tr>"
            "<tr><td>e</td><td>f</td></tr></table>")
    assert table_teds(html, _grid()) < 1.0


def test_both_empty_is_one_missing_table_is_zero():
    assert table_teds("", None) == 1.0
    assert table_teds("<table><tr><td>a</td></tr></table>", None) == 0.0


def test_sidecar_splits_multiple_tables():
    from scripts.eval_table import _ref_tables
    html = ("<table><tr><td>1</td></tr></table>\n"
            "<TABLE><tr><td>2</td></tr></TABLE>")
    assert len(_ref_tables(html)) == 2
