"""Cross-page paragraph continuation (Area D, D3) — FLOW output only.

A paragraph broken by a page break arrives as two blocks: the tail of page N and the head of page
N+1. On a LAYOUT-faithful render each page is kept verbatim, so they stay split (the deliberate
per-page-fidelity decision). But a FLOW render reflows the text, and there the split is pure
damage: the translator sees two half-sentences (worse context, a mid-thought fragment) and the
output shows a broken paragraph. So for flow outputs only, rejoin them BEFORE translation.

Conservative — merge a pair only when it really looks like one paragraph carried over:
  - both are body PARAGRAPHs (not heading/caption/list/footnote/figure …)
  - the page-N tail does NOT end on a sentence terminator (. ! ?) — an open clause continues
  - the page-N+1 head continues it: starts lowercase/'(' , or the tail ends on a hyphen
A hyphen at the break is de-hyphenated ("inter-" + "national" -> "international").
"""

from __future__ import annotations

from ..ir import BlockType, Document

_TERMINATORS = (".", "!", "?", "．", "。", "！", "？")


def _continues(tail: str, head: str) -> bool:
    t, h = tail.rstrip(), head.lstrip()
    if not t or not h:
        return False
    if t.endswith("-"):                       # hyphenated word split across the page break
        return True
    if t[-1] in _TERMINATORS or t[-1] in ")]”\"'":   # a closed sentence rarely runs on
        return False
    first = h[0]
    return first.islower() or first.isdigit() or first in "(,;:"


def _join(tail: str, head: str) -> str:
    t, h = tail.rstrip(), head.lstrip()
    if t.endswith("-"):
        return t[:-1] + h                     # de-hyphenate: drop the hyphen, no space
    return t + " " + h


def merge_cross_page(doc: Document) -> int:
    """Rejoin paragraphs split across a page break (flow output). Returns the count merged.
    In place; the head block is removed and its text folded into the tail block."""
    by_page: dict[int, list] = {}
    for b in doc.ordered_blocks():
        by_page.setdefault(b.page, []).append(b)
    pages = sorted(by_page)
    drop: set[int] = set()
    for pno, nxt in zip(pages, pages[1:]):
        if nxt != pno + 1:                    # only true adjacent pages
            continue
        tail = next((b for b in reversed(by_page[pno])
                     if b.type == BlockType.PARAGRAPH and b.text.strip()
                     and id(b) not in drop), None)
        head = next((b for b in by_page[nxt]
                     if b.type == BlockType.PARAGRAPH and b.text.strip()), None)
        if not tail or not head:
            continue
        if _continues(tail.text, head.text):
            tail.text = _join(tail.text, head.text)
            drop.add(id(head))
    if not drop:
        return 0
    before = len(doc.blocks)
    doc.blocks = [b for b in doc.blocks if id(b) not in drop]
    return before - len(doc.blocks)
