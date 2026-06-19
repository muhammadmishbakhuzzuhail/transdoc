# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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
    wb.save(out_path)
    return out_path
