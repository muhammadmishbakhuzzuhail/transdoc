# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Reproducible output-fidelity QA. For each output PDF it flags, per page:
  - OVERWRITE: a text span whose bbox overlaps an embedded image (raster/crop) — text drawn
    on top of a figure/table crop ("menimpa tidak rapi").
  - TINY:      a span rendered < 6 pt (illegible).
  - OVERFLOW:  a span whose bbox leaves the page rect.
  - coverage:  per-page text-span count, image count, mean font size.
Run: python scripts/qa_fidelity.py out/<file>.pdf [more.pdf ...]
No torch/paddle needed — pure PyMuPDF geometry. This makes the review repeatable instead of
eyeballed."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# The audit lives in the eval package now (one source of truth); keep the CLI here.
from transdoc.eval.metrics import pdf_fidelity as audit  # noqa: E402


def main() -> None:
    for path in sys.argv[1:]:
        f = audit(path)
        print(f"\n{'='*70}\n{path}")
        ow, tn, of = f["overwrite"], f["tiny"], f["overflow"]
        print(f"  OVERWRITE (text on image): {len(ow)}   TINY (<6pt): {len(tn)}   "
              f"OVERFLOW: {len(of)}")
        for tag, items in (("OVERWRITE", ow), ("TINY", tn)):
            for it in items[:8]:
                print(f"    [{tag}] p{it[0]} {it[1]}pt  {it[2]!r}")
            if len(items) > 8:
                print(f"    ... +{len(items)-8} more")
        for it in of[:5]:
            print(f"    [OVERFLOW] p{it[0]} {it[1]!r}")
        # page coverage summary
        dense = [p for p in f["pages"] if p["font_min"] and p["font_min"] < 6]
        print(f"  pages={len(f['pages'])}  pages_with_subpt_font={len(dense)}")


if __name__ == "__main__":
    main()
