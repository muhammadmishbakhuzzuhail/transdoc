# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Cross-page running header/footer + page-number removal.

Research (deep-research 2026-06-15): mature tools (MinerU) drop running headers, footers and
page numbers by classifying them as 'discard' regions; a robust signal is *cross-page
repetition* — the same short text recurring in the top/bottom margin of many pages. Layout
models mislabel these often, and on a clean reflow they are noise (and waste translation calls).

Conservative: only fires on multi-page docs; only short text in the top/bottom margin band that
repeats on a majority of pages (page numbers normalized so "Page 3"/"Page 4" count as one).
"""

from __future__ import annotations

import re

_MARGIN = 0.12          # top/bottom 12% of the page height
_MIN_PAGES = 3
_MAX_LEN = 80           # headers/footers are short
_DIGITS = re.compile(r"\d+")


def _norm(s: str) -> str:
    # collapse whitespace + mask numbers so "Page 3" and "Page 4" group together
    return _DIGITS.sub("#", " ".join((s or "").lower().split()))


def drop_repeated(doc) -> int:
    """Drop running headers/footers/page-numbers detected by cross-page repetition in the
    margins. Returns the count removed. In place."""
    npages = doc.page_count or 0
    if npages < _MIN_PAGES or not doc.page_sizes:
        return 0

    text_types = {"paragraph", "heading", "title", "caption", "footer", "header", "page_number"}
    # group margin-band short text -> set of pages it appears on
    groups: dict[str, set[int]] = {}
    members: dict[str, list] = {}
    for b in doc.blocks:
        if b.type.value not in text_types or not b.bbox:
            continue
        t = (b.text or "").strip()
        if not t or len(t) > _MAX_LEN:
            continue
        ph = doc.page_sizes.get(b.page, (0, 0))[1] or 0
        if ph <= 0:
            continue
        in_top = b.bbox.y1 <= ph * _MARGIN
        in_bottom = b.bbox.y0 >= ph * (1 - _MARGIN)
        if not (in_top or in_bottom):
            continue
        key = _norm(t)
        if not key:
            continue
        groups.setdefault(key, set()).add(b.page)
        members.setdefault(key, []).append(b)

    threshold = max(_MIN_PAGES, npages // 2)
    drop_ids = set()
    for key, pages in groups.items():
        if len(pages) >= threshold:
            for b in members[key]:
                drop_ids.add(id(b))
    if not drop_ids:
        return 0
    before = len(doc.blocks)
    doc.blocks = [b for b in doc.blocks if id(b) not in drop_ids]
    return before - len(doc.blocks)
