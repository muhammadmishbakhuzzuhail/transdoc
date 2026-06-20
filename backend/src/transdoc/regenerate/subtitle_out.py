# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""SRT / WebVTT renderer — round-trip. Re-parse the source, swap each cue's TEXT lines with
its translation (by cue id), keep every timestamp/header verbatim, re-serialize."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..extract.subtitle import _read, compose_cues, parse_cues
from ..ir import Document


def render(doc: Document, cfg: Config, out_path: str) -> str:
    # charset-detect like the extractor (_read). A hardcoded utf-8 re-read mangled non-UTF-8 files
    # (UTF-16 from Windows tools): embedded NULs broke the blank-line cue split, desyncing cue ids.
    src = _read(doc.source_path)
    m = {b.id: b.output_text for b in doc.blocks}
    cues = parse_cues(src)
    for i, cue in enumerate(cues):
        tr = m.get(f"cue{i}")
        if tr is not None:
            cue["text"] = tr.split("\n")
    Path(out_path).write_text(compose_cues(cues), encoding="utf-8")
    return out_path
