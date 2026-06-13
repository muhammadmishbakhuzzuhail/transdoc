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
