# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""PowerPoint (.pptx) extraction via python-pptx.

One IR block per text-bearing paragraph (in shapes and table cells), with a stable id that
encodes its location (slide/shape/paragraph). The renderer reopens the source deck and swaps
text by that id, so every visual property — theme, position, fonts, animations — is kept.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Confidence, Document
from .base import reflow_order


def _para_text(para) -> str:
    return "".join(run.text for run in para.runs)


def extract(path: str, cfg: Config) -> Document:
    from pptx import Presentation

    try:
        prs = Presentation(path)
    except Exception as e:
        raise ValueError(f"unreadable or corrupt PPTX: {e}") from e
    out = Document(source_path=path,
                   mime="application/vnd.openxmlformats-officedocument.presentationml.presentation")
    for si, slide in enumerate(prs.slides):
        for shi, shape in enumerate(slide.shapes):
            if shape.has_text_frame:
                for pi, para in enumerate(shape.text_frame.paragraphs):
                    t = _para_text(para)
                    if t.strip():
                        out.blocks.append(Block(
                            id=f"s{si}_sh{shi}_p{pi}", type=BlockType.PARAGRAPH, page=si,
                            text=t, confidence=Confidence(source="digital")))
            elif shape.has_table:
                for ri, row in enumerate(shape.table.rows):
                    for ci, cell in enumerate(row.cells):
                        for pi, para in enumerate(cell.text_frame.paragraphs):
                            t = _para_text(para)
                            if t.strip():
                                out.blocks.append(Block(
                                    id=f"s{si}_sh{shi}_t{ri}_{ci}_p{pi}",
                                    type=BlockType.PARAGRAPH, page=si, text=t,
                                    confidence=Confidence(source="digital")))
    reflow_order(out)
    return out
