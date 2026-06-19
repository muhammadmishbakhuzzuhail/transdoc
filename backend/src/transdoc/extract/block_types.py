# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Block-typing enrichment (Area D, D2): running headers/footers + page numbers.

The font-size heuristic types blocks TITLE/HEADING/PARAGRAPH but is blind to page furniture — a
running head, a footer, a page number. They live in the top/bottom margin and (for head/foot)
REPEAT across pages, which is exactly how to tell a running head from a heading that happens to sit
high on a short page. Detected here so both extract paths (heuristic + structured) get the richer
types: page numbers become non-translatable (digits, not prose) and the reading order/analysis can
treat furniture as furniture.

Conservative: only upgrades non-specific types (PARAGRAPH/OTHER/HEADING/TITLE); never clobbers a
CAPTION/FOOTNOTE/TABLE/FORMULA already assigned. A title appears once, so repetition leaves it be.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..ir import Block, BlockType, Document

_MARGIN = 0.10            # top/bottom 10% of the page is the header/footer band
_SIDE_MARGIN = 0.15       # outer left/right 15% is the marginalia band
_SIDE_MAX_W = 0.20        # marginalia is narrow — at most 20% of the page width
_BODY_MIN_W = 0.40        # a "body" block (the main text the note sits beside) is wider than this
_UPGRADABLE = {BlockType.PARAGRAPH, BlockType.OTHER, BlockType.HEADING, BlockType.TITLE}
# a page-number cell: a short run of digits / roman numerals, optionally "Page 3" or "3 / 10"
_PAGENUM = re.compile(r"(?:page\s+)?[\divxlcm]+(?:\s*[/of-]+\s*[\divxlcm]+)?\.?", re.IGNORECASE)


def _norm(t: str) -> str:
    """Repetition key: drop digits + punctuation so '3 Introduction' on every page collapses."""
    return re.sub(r"[\d\W]+", " ", t.lower()).strip()


def _is_pagenum(t: str) -> bool:
    s = t.strip()
    return bool(s) and len(s) <= 12 and bool(_PAGENUM.fullmatch(s))


def detect_running_heads(doc: Document) -> None:
    """Tag margin blocks: numeric margin cells -> PAGE_NUMBER; margin text repeating across pages
    -> HEADER/FOOTER. Operates on positioned blocks; safe to run on either extract path."""
    cand: list[tuple[Block, str]] = []      # (block, "head" | "foot")
    pages: set[int] = set()
    for b in doc.blocks:
        if not b.bbox:
            continue
        pages.add(b.page)
        ph = (doc.page_sizes.get(b.page, (595.0, 842.0))[1]) or 842.0
        ymid = (b.bbox.y0 + b.bbox.y1) / 2
        if ymid < _MARGIN * ph:
            cand.append((b, "head"))
        elif ymid > (1 - _MARGIN) * ph:
            cand.append((b, "foot"))
    if not cand:
        return

    # page numbers first (they shouldn't count toward running-head repetition)
    for b, _band in cand:
        if b.type in _UPGRADABLE and _is_pagenum(b.text):
            b.type = BlockType.PAGE_NUMBER

    # repetition: same normalised text in the same band on enough pages = running head/foot
    groups: dict[tuple[str, str], list[Block]] = defaultdict(list)
    seen_pages: dict[tuple[str, str], set[int]] = defaultdict(set)
    for b, band in cand:
        if b.type == BlockType.PAGE_NUMBER:
            continue
        key = (band, _norm(b.text))
        if not key[1]:
            continue
        groups[key].append(b)
        seen_pages[key].add(b.page)
    need = max(2, round(len(pages) * 0.5))
    for key, blocks in groups.items():
        if len(seen_pages[key]) < need:
            continue
        target = BlockType.HEADER if key[0] == "head" else BlockType.FOOTER
        for b in blocks:
            if b.type in _UPGRADABLE:
                b.type = target


def detect_marginalia(doc: Document) -> None:
    """Tag side notes / marginalia: a NARROW block in the outer left/right margin sitting BESIDE a
    wider body block (not page furniture, not a column). Kept + translated as ASIDE. Conservative —
    a body column is too wide (> _SIDE_MAX_W) to qualify, so two-column layouts are unaffected."""
    by_page: dict[int, list[Block]] = {}
    for b in doc.blocks:
        if b.bbox:
            by_page.setdefault(b.page, []).append(b)
    for pno, blocks in by_page.items():
        pw = (doc.page_sizes.get(pno, (595.0, 842.0))[0]) or 595.0
        bodies = [b for b in blocks if (b.bbox.x1 - b.bbox.x0) > _BODY_MIN_W * pw]
        if not bodies:
            continue
        for b in blocks:
            if b.type not in _UPGRADABLE:
                continue
            w = b.bbox.x1 - b.bbox.x0
            if w > _SIDE_MAX_W * pw:
                continue
            in_left = b.bbox.x1 <= _SIDE_MARGIN * pw
            in_right = b.bbox.x0 >= (1 - _SIDE_MARGIN) * pw
            if not (in_left or in_right):
                continue
            # must sit beside a body block (vertical overlap) — else it's a stray narrow line
            beside = any(min(b.bbox.y1, body.bbox.y1) - max(b.bbox.y0, body.bbox.y0) > 0
                         for body in bodies if body is not b)
            if beside:
                b.type = BlockType.ASIDE
