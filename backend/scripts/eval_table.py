# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Table-structure accuracy eval (TEDS-Struct).

The structure gate counts table cells, but the count is invariant to catastrophic grid errors —
cells in the wrong row, dropped/added spans, merged-vs-split cells. This scores the *shape*: for
each document with a `<stem>.tables.html` reference sidecar (the source tables as HTML, in reading
order), it extracts via the pipeline and compares each extracted IR Table to its reference with
TEDS-Struct (1.0 = identical grid). Closes the "no positional/structural table metric" gap.

Reference sidecar format — one HTML file per doc, containing one `<table>...</table>` per table in
reading order (only the grid + row/colspan matter; cell text is ignored by TEDS-Struct):

    <table><tr><td>Name</td><td>Value</td></tr><tr><td>A</td><td>1</td></tr></table>

Bring your own references (not committed). Deterministic (engine=echo); local/opt-in.

    cd backend && .venv/bin/python -m scripts.eval_table path/to/doc.pdf [more docs...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


def _ref_tables(html: str) -> list[str]:
    """Split a sidecar into individual <table>...</table> strings (reading order)."""
    return re.findall(r"<table\b.*?</table>", html, flags=re.IGNORECASE | re.DOTALL)


def _doc_tables(path: str):
    """Extract the doc and return its TABLE blocks' IR Tables in reading order."""
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect
    from transdoc.ir import BlockType

    doc = extract(detect(path), Config(target_lang="id"))
    return [b.table for b in sorted(doc.blocks, key=lambda b: (b.page, b.reading_order))
            if b.type == BlockType.TABLE and b.table is not None]


def main(argv: list[str]) -> int:
    from transdoc.eval.metrics import table_teds

    if not argv:
        sys.stderr.write("usage: eval_table <doc> [<doc> ...]  (each needs a <stem>.tables.html)\n")
        return 2
    print(f"{'file':30} {'tables':>6} {'TEDS-Struct':>12}")
    print("-" * 52)
    all_scores: list[float] = []
    for path in argv:
        sidecar = Path(path).with_suffix(".tables.html")
        if not sidecar.exists():
            print(f"{Path(path).name[:30]:30} {'(no .tables.html ref)':>19}")
            continue
        refs = _ref_tables(sidecar.read_text(encoding="utf-8"))
        try:
            hyps = _doc_tables(path)
        except Exception as e:
            print(f"{Path(path).name[:30]:30} ERROR {type(e).__name__}: {e}")
            continue
        # pair by reading order; a missing/extra table scores 0 for that slot
        n = max(len(refs), len(hyps))
        scores = [table_teds(refs[i] if i < len(refs) else "",
                             hyps[i] if i < len(hyps) else None) for i in range(n)]
        mean = sum(scores) / len(scores) if scores else 1.0
        all_scores.extend(scores)
        print(f"{Path(path).name[:30]:30} {len(hyps):>6} {mean:>12.3f}")
    if all_scores:
        print("-" * 52)
        print(f"{'mean':30} {'':>6} {sum(all_scores) / len(all_scores):>12.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
