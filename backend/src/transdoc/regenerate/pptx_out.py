# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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

    from ..extract.pptx import iter_text_paras   # one shared walk -> extract/render never drift

    m = {b.id: b.output_text for b in doc.blocks}
    prs = Presentation(doc.source_path)
    for bid, para, _si in iter_text_paras(prs):
        t = m.get(bid)
        if t is not None:
            _set_para(para, t)
    prs.save(out_path)
    return out_path
