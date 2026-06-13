"""XLSX extraction shape depends on the output format.

* Round-trip (xlsx / same-as-source): one block per text cell, keyed by coordinate, so the
  renderer writes each translation back in place.
* Cross-format (md/docx/pdf/plain): one TABLE block per sheet, so the grid survives instead
  of flattening into a one-cell-per-line list.
"""

from __future__ import annotations

import pytest

pytest.importorskip("openpyxl")

from openpyxl import Workbook  # noqa: E402

from transdoc.config import Config, OutputFormat  # noqa: E402
from transdoc.extract.xlsx import extract  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402


def _make_xlsx(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Name", "City"])
    ws.append(["Hello", "London"])
    wb.save(path)


def test_xlsx_roundtrip_is_per_cell(tmp_path):
    src = tmp_path / "s.xlsx"
    _make_xlsx(str(src))
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.XLSX))
    assert all(b.type == BlockType.PARAGRAPH for b in doc.blocks)
    assert {b.id for b in doc.blocks} == {"Sheet!A1", "Sheet!B1", "Sheet!A2", "Sheet!B2"}


def test_xlsx_crossformat_is_a_table(tmp_path):
    src = tmp_path / "s.xlsx"
    _make_xlsx(str(src))
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.MARKDOWN))
    tables = [b for b in doc.blocks if b.type == BlockType.TABLE]
    assert len(tables) == 1
    rows = tables[0].table.rows
    assert [c.text for c in rows[0]] == ["Name", "City"]
    assert [c.text for c in rows[1]] == ["Hello", "London"]
