# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""XLSX renderer — round-trip. Reopen the workbook, write translations back to the same
cell coordinates, keeping styles, widths, merges, and formulas untouched."""

from __future__ import annotations

from ..config import Config
from ..ir import Document


def render(doc: Document, cfg: Config, out_path: str) -> str:
    import openpyxl

    m = {b.id: b.output_text for b in doc.blocks}
    wb = openpyxl.load_workbook(doc.source_path, data_only=False)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                t = m.get(f"{ws.title}!{cell.coordinate}")
                if t is not None:
                    cell.value = t
                    # a translation starting with "=" (or a CSV-injection sigil) would be stored as
                    # a live formula by openpyxl. Translations are always prose, never formulas
                    # (source formula cells are skipped at extract), so pin them to a string cell.
                    if isinstance(t, str) and t[:1] in ("=", "+", "-", "@"):
                        cell.data_type = "s"
    wb.save(out_path)
    return out_path
