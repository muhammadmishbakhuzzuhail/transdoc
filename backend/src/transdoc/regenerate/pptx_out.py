# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""PPTX renderer — round-trip. Reopen the source deck, walk it identically to the extractor,
and write each translated paragraph into its first run (clearing the rest), preserving the
deck's theme, layout, and positioning."""

from __future__ import annotations

from ..config import Config
from ..ir import Document


def _set_para(para, text: str) -> None:
    if not para.runs:
        return
    para.runs[0].text = text
    for run in para.runs[1:]:
        run.text = ""


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from pptx import Presentation

    m = {b.id: b.output_text for b in doc.blocks}
    prs = Presentation(doc.source_path)
    for si, slide in enumerate(prs.slides):
        for shi, shape in enumerate(slide.shapes):
            if shape.has_text_frame:
                for pi, para in enumerate(shape.text_frame.paragraphs):
                    t = m.get(f"s{si}_sh{shi}_p{pi}")
                    if t is not None:
                        _set_para(para, t)
            elif shape.has_table:
                for ri, row in enumerate(shape.table.rows):
                    for ci, cell in enumerate(row.cells):
                        for pi, para in enumerate(cell.text_frame.paragraphs):
                            t = m.get(f"s{si}_sh{shi}_t{ri}_{ci}_p{pi}")
                            if t is not None:
                                _set_para(para, t)
    prs.save(out_path)
    return out_path
