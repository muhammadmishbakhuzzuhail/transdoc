# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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


def column_reading_order(doc: Document) -> None:
    """Multi-column-aware reading order. Delegates to the recursive XY-cut in
    ``reading_order`` (the single source of truth for both extract paths); kept as a named
    entry point for the heuristic PDF path and its tests."""
    from .reading_order import reading_order
    reading_order(doc)


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


def snap_captions(doc: Document) -> None:
    """Re-assert caption→media adjacency at render time using the durable ``anchor_id`` link.

    ``associate_captions`` sets ``anchor_id`` and nudges reading order at extraction, but the
    intervening stages (reading-order re-rank, flow merges, vertical-reorder, cross-page merge) all
    renumber ``reading_order`` and can drift a caption away from its figure/table. ``anchor_id``
    survives those renumberings, so just before regeneration we snap each caption back to sit
    immediately after (caption below) or before (caption above) its anchor. Idempotent; no-op when
    no block carries an ``anchor_id``."""
    by_id = {b.id: b for b in doc.blocks}
    anchored = [b for b in doc.blocks if getattr(b, "anchor_id", None) in by_id]
    if not anchored:
        return
    key: dict[str, float] = {}
    for cap in anchored:
        media = by_id[cap.anchor_id]
        below = bool(cap.bbox and media.bbox and cap.bbox.y0 >= media.bbox.y0)
        key[cap.id] = media.reading_order + (0.5 if below else -0.5)
    ordered = sorted(doc.blocks, key=lambda b: key.get(b.id, float(b.reading_order)))
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
