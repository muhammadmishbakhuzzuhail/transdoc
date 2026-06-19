# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Document-level translation consistency (DeepL-style).

A per-segment translator can render the SAME source sentence two different ways in one document
(a heading repeated, a boilerplate line, a table label). DeepL reads the document as one coherent
unit; we approximate that with a deterministic post-translate pass: group segments by normalised
source and force one translation across each group.

Winner per group: a human-confirmed correction if one exists, else the majority translation, else
the first occurrence. Harmonised segments are flagged so the report/review shows what changed.
"""

from __future__ import annotations

import re
from collections import Counter

from ..config import Config
from ..ir import Document


def _norm(text: str) -> str:
    """Match key: collapse whitespace + case-fold so 'Total ' and 'total' group together."""
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def enforce_consistency(doc: Document, cfg: Config) -> int:
    """Force one translation per identical source across the document. Returns the count changed."""
    groups: dict[str, list] = {}
    for b in doc.blocks:
        if b.is_translatable and b.translated is not None and b.text.strip():
            groups.setdefault(_norm(b.text), []).append(b)

    tm = None
    try:
        from ..store.tm import TMStore
        tm = TMStore.get()
    except Exception:
        tm = None

    changed = 0
    for blocks in groups.values():
        translations = [b.translated for b in blocks]
        if len(set(translations)) <= 1:
            continue
        winner = None
        if tm is not None:
            try:
                winner = tm.confirmed_translation(blocks[0].text, cfg.target_lang) or None
            except Exception:
                winner = None
        if not winner:
            # majority; Counter.most_common is stable on ties -> first occurrence wins
            winner = Counter(translations).most_common(1)[0][0]
        for b in blocks:
            if b.translated != winner:
                b.translated = winner
                b.flags["consistency_normalized"] = (
                    "harmonised with the same source text elsewhere in the document")
                changed += 1
    return changed
