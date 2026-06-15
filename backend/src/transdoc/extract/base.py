"""Extractor protocol + shared helpers. Each extractor produces an IR Document."""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..ir import Block, Document


class Extractor(Protocol):
    def extract(self, path: str, cfg: Config) -> Document: ...


def block_id(page: int, idx: int) -> str:
    return f"p{page}-b{idx}"


def reflow_order(doc: Document) -> None:
    """Assign a global reading_order from (page, existing order) if unset."""
    for i, b in enumerate(doc.ordered_blocks()):
        b.reading_order = i


def _try_columns(band: list[Block], pw: float, k: int) -> list[Block] | None:
    """Try to read a band as k equal-width columns. Assign each block to the column its centre
    lands in; accept only if the split is clean — at least 2 columns are non-empty and every
    block sits within its column strip (no block straddles a boundary, tol = 3% page width).
    Returns the column-by-column (each top-to-bottom) order, or None if it isn't a clean k-split."""
    if k < 2 or len(band) < k:
        return None
    cw = pw / k
    tol = pw * 0.03
    cols: list[list[Block]] = [[] for _ in range(k)]
    for b in band:
        c = (b.bbox.x0 + b.bbox.x1) / 2
        idx = min(k - 1, max(0, int(c // cw)))
        lo, hi = idx * cw, (idx + 1) * cw
        if b.bbox.x0 < lo - tol or b.bbox.x1 > hi + tol:
            return None                     # a block straddles a column boundary -> not k-col
        cols[idx].append(b)
    if sum(1 for col in cols if col) < 2:
        return None                         # everything in one column -> not multi-column
    out: list[Block] = []
    for col in cols:
        out += sorted(col, key=lambda b: b.bbox.y0)
    return out


def _order_band(band: list[Block], pw: float) -> list[Block]:
    """Order a horizontal band of blocks: if it splits cleanly into equal-width columns
    (3 then 2 — disjoint, no straddling), read each column top-to-bottom in turn; else
    top-to-bottom."""
    if len(band) <= 1:
        return band
    for k in (3, 2):
        ordered = _try_columns(band, pw, k)
        if ordered is not None:
            return ordered
    return sorted(band, key=lambda b: (b.bbox.y0, b.bbox.x0))


def column_reading_order(doc: Document) -> None:
    """Assign reading_order handling multi-column layouts. Naively sorting blocks by y
    interleaves columns (research: PyMuPDF order ≠ reading order on multi-column pages). Per
    page: full-width blocks (>60% of page width — titles, rules, wide figures) break the page
    into bands; within each band a clean 3- or 2-column split is read column-by-column; otherwise
    top-to-bottom. Single-column pages are unaffected."""
    order = 0
    by_page: dict[int, list[Block]] = {}
    for b in doc.blocks:
        by_page.setdefault(b.page, []).append(b)
    for pno in sorted(by_page):
        page_blocks = by_page[pno]
        positioned = sorted((b for b in page_blocks if b.bbox),
                            key=lambda b: (b.bbox.y0, b.bbox.x0))
        pw = doc.page_sizes.get(pno, (595.0, 842.0))[0] or 595.0
        result: list[Block] = []
        band: list[Block] = []
        for b in positioned:
            if (b.bbox.x1 - b.bbox.x0) > 0.6 * pw:     # full-width -> flush band, then place it
                result += _order_band(band, pw)
                band = []
                result.append(b)
            else:
                band.append(b)
        result += _order_band(band, pw)
        for b in result:
            b.reading_order = order
            order += 1
        for b in (b for b in page_blocks if not b.bbox):   # no-geometry blocks keep append order
            b.reading_order = order
            order += 1


def associate_captions(doc: Document) -> None:
    """Bind each CAPTION to the nearest figure/table it describes and snap reading order so the
    two stay adjacent. A caption that the layout model floated (or a bbox sort that slotted a
    body paragraph between a figure and its caption) would otherwise separate them. Convention:
    a caption below its media renders after it, a caption above (typical for tables) before it.
    bbox-only — the office paths produce no positioned figures and are unaffected."""
    from ..ir import BlockType
    media = [b for b in doc.blocks if b.type in (BlockType.FIGURE, BlockType.TABLE) and b.bbox]
    caps = [b for b in doc.blocks if b.type == BlockType.CAPTION and b.bbox]
    if not media or not caps:
        return
    nudged: dict[str, float] = {}
    for cap in caps:
        best, best_gap = None, None
        for m in media:
            if m.page != cap.page:
                continue
            overlap = min(cap.bbox.x1, m.bbox.x1) - max(cap.bbox.x0, m.bbox.x0)
            if overlap <= 0:                      # not in the same column band
                continue
            gap = max(cap.bbox.y0 - m.bbox.y1, m.bbox.y0 - cap.bbox.y1, 0.0)
            if best_gap is None or gap < best_gap:
                best, best_gap = m, gap
        if best is None:
            continue
        cap.anchor_id = best.id
        below = cap.bbox.y0 >= best.bbox.y0       # caption starts lower than its media
        nudged[cap.id] = best.reading_order + (0.5 if below else -0.5)
    if not nudged:
        return
    # renumber to dense integers, captions sitting next to their anchor via the fractional key
    ordered = sorted(doc.blocks, key=lambda b: nudged.get(b.id, float(b.reading_order)))
    for i, b in enumerate(ordered):
        b.reading_order = i


def _is_vertical(b: Block) -> bool:
    """A tall, very narrow box = rotated/vertical sidebar text (e.g. an arXiv ID)."""
    if not b.bbox:
        return False
    w = b.bbox.x1 - b.bbox.x0
    h = b.bbox.y1 - b.bbox.y0
    return w < 40 and h > w * 4


def reorder_vertical_last(doc: Document) -> None:
    """FLOW reading order: move rotated/vertical sidebar blocks to the end of their page so a
    margin identifier doesn't interrupt the reflowed text. Relative order is otherwise kept."""
    from itertools import groupby

    ordered = doc.ordered_blocks()                    # already sorted by (page, reading_order)
    out: list[Block] = []
    for _page, grp in groupby(ordered, key=lambda b: b.page):
        g = list(grp)
        out += [b for b in g if not _is_vertical(b)]
        out += [b for b in g if _is_vertical(b)]
    for i, b in enumerate(out):
        b.reading_order = i


def merge_block(blocks: list[Block]) -> str:
    return "\n\n".join(b.text for b in blocks if b.text.strip())
