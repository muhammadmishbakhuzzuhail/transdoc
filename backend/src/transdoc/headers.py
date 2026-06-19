# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Running header/footer detection.

A page header or footer (running title, journal name, page number band) repeats on most
pages. In LAYOUT output it stays in place and is harmless, but in FLOW output (->DOCX/MD)
it clutters the reflowed text and wastes translation calls. This pass drops blocks whose
text repeats, in the top/bottom band, across most pages. FLOW-only — call it after diagnose
and before translate.
"""

from __future__ import annotations

from collections import defaultdict

from .ir import BlockType, Document

_BAND = 0.10          # top/bottom 10% of the page height = header/footer band
_MAX_LEN = 120        # running headers are short; don't drop a long paragraph by accident


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def strip_running_headers(doc: Document) -> int:
    """Remove repeating header/footer blocks in place. Returns the number removed."""
    heights = {pno: h for pno, (w, h) in doc.page_sizes.items()}
    npages = doc.page_count or len(heights) or 1
    if npages < 3:
        return 0  # too few pages to tell a running header from real content

    def in_band(b) -> bool:
        h = heights.get(b.page, 0) or 0
        return bool(b.bbox and h > 0 and (b.bbox.y0 < h * _BAND or b.bbox.y1 > h * (1 - _BAND)))

    pages_by_text: dict[str, set[int]] = defaultdict(set)
    for b in doc.blocks:
        if b.type == BlockType.FIGURE or not in_band(b):
            continue
        norm = _norm(b.text)
        if norm and len(norm) <= _MAX_LEN:
            pages_by_text[norm].add(b.page)

    threshold = max(3, int(npages * 0.4))
    repeated = {t for t, ps in pages_by_text.items() if len(ps) >= threshold}
    if not repeated:
        return 0

    kept, removed = [], 0
    for b in doc.blocks:
        if in_band(b) and _norm(b.text) in repeated:
            removed += 1
            continue
        kept.append(b)
    doc.blocks = kept
    return removed
