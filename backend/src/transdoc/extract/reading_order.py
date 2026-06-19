# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Reading-order assignment via recursive XY-cut (Area D, D1).

One source of truth for both the heuristic PDF path and the PP-StructureV3 structured path: given
typed blocks with bboxes, compute the order a human reads them. Recursive XY-cut generalises the
old equal-width band split — it cuts at the widest WHITESPACE gutter, so it handles unequal
columns (a wide body + a narrow sidebar), nested structure (columns inside a band), 3+ columns,
and floats (a bottom footnote sorts last because it's spatially last). No model, deterministic,
CPU-free.

Algorithm, per page, recursively over a set of blocks:
  1. If a full-height VERTICAL gutter (≥ min_gap_v) separates the blocks into left/right groups,
     cut there and read left group fully, then right — columns dominate reading order.
  2. Else if a full-width HORIZONTAL gap (≥ min_gap_h) separates them into top/bottom, cut there
     (a title above columns, a footer below) and read top then bottom.
  3. Else order what's left top-to-bottom, then left-to-right.
Vertical is tried first on purpose: preferring the larger gap would split a two-column page into
rows and interleave the columns.
"""

from __future__ import annotations

from ..ir import Block, Document


def _largest_gap(intervals: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Merge 1-D intervals (a projection of the blocks onto one axis) and return the largest gap
    between consecutive merged runs as (width, lo_edge, hi_edge), or None if they all touch."""
    merged: list[list[float]] = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    best: tuple[float, float, float] | None = None
    for i in range(len(merged) - 1):
        gap = merged[i + 1][0] - merged[i][1]
        if best is None or gap > best[0]:
            best = (gap, merged[i][1], merged[i + 1][0])
    return best


def _xy_cut(blocks: list[Block], min_gap_v: float, min_gap_h: float) -> list[Block]:
    if len(blocks) <= 1:
        return list(blocks)

    vg = _largest_gap([(b.bbox.x0, b.bbox.x1) for b in blocks])
    if vg and vg[0] >= min_gap_v:
        cut = (vg[1] + vg[2]) / 2
        left = [b for b in blocks if (b.bbox.x0 + b.bbox.x1) / 2 < cut]
        right = [b for b in blocks if (b.bbox.x0 + b.bbox.x1) / 2 >= cut]
        if left and right:
            return (_xy_cut(left, min_gap_v, min_gap_h)
                    + _xy_cut(right, min_gap_v, min_gap_h))

    hg = _largest_gap([(b.bbox.y0, b.bbox.y1) for b in blocks])
    if hg and hg[0] >= min_gap_h:
        cut = (hg[1] + hg[2]) / 2
        top = [b for b in blocks if (b.bbox.y0 + b.bbox.y1) / 2 < cut]
        bot = [b for b in blocks if (b.bbox.y0 + b.bbox.y1) / 2 >= cut]
        if top and bot:
            return (_xy_cut(top, min_gap_v, min_gap_h)
                    + _xy_cut(bot, min_gap_v, min_gap_h))

    return sorted(blocks, key=lambda b: (b.bbox.y0, b.bbox.x0))


def reading_order(doc: Document) -> None:
    """Assign a global reading_order across pages via per-page XY-cut. Blocks without a bbox
    (office formats) keep their append order at the end of their page."""
    order = 0
    by_page: dict[int, list[Block]] = {}
    for b in doc.blocks:
        by_page.setdefault(b.page, []).append(b)
    for pno in sorted(by_page):
        page_blocks = by_page[pno]
        pw, ph = doc.page_sizes.get(pno, (595.0, 842.0))
        # gutter must be a real column gap, not inter-word space; horizontal cuts can be small
        # (separate a title/footer) since over-splitting vertically is what interleaves columns.
        min_gap_v = max(15.0, 0.02 * (pw or 595.0))
        min_gap_h = max(8.0, 0.01 * (ph or 842.0))
        positioned = [b for b in page_blocks if b.bbox]
        for b in _xy_cut(positioned, min_gap_v, min_gap_h):
            b.reading_order = order
            order += 1
        for b in page_blocks:                 # no-geometry blocks keep append order, after
            if not b.bbox:
                b.reading_order = order
                order += 1
