# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Reading-order accuracy eval (Area D, D1).

eval_layout scores WHERE regions are (IoU) and WHAT they are (label) — but not the ORDER they're
read in, which is what the XY-cut produces and what a translation's flow depends on. This scores
the order: for each doc with a `<stem>.order.json` reference (the blocks' bboxes in correct reading
order), it extracts via the pipeline, takes the blocks in `reading_order`, and compares with
Kendall-tau (rank correlation) + sequence accuracy (adjacent pairs kept in order).

Reference sidecar — one JSON per doc, a list of boxes in reading order (page-0 by default; pass
--page to score another page). Bring your own (not committed). Deterministic (engine not used —
extraction only); local/opt-in.

    [{"bbox": [x0, y0, x1, y1]}, {"bbox": [..]}, ...]

    cd backend && .venv/bin/python -m scripts.eval_reading_order path/to/doc.pdf [more docs...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _hyp_boxes(path: str, page: int, reading_order: str = "xycut",
               ) -> list[tuple[float, float, float, float]]:
    """Extract the doc and return page `page` blocks' bboxes in reading order. With
    reading_order='surya', apply the Surya re-rank (the same step the pipeline runs) before reading
    the order off — so xycut vs surya can be compared head-to-head."""
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    cfg = Config(target_lang="id", reading_order_engine=reading_order)
    doc = extract(detect(path), cfg)
    if reading_order == "surya":
        from transdoc.extract.surya_order import surya_reading_order
        surya_reading_order(doc, cfg)
    # Mirror the FLOW pipeline: margin/rotated furniture (e.g. an arXiv side stamp) is pushed to the
    # end of its page before translation. Measure the order the document is actually read in, not the
    # raw extractor order.
    from transdoc.extract.base import reorder_vertical_last
    reorder_vertical_last(doc)
    return [(b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
            for b in doc.ordered_blocks() if b.page == page and b.bbox]


def main(argv: list[str]) -> int:
    from transdoc.eval.metrics import reading_order_match

    ap = argparse.ArgumentParser(description="reading-order accuracy eval (Area D)")
    ap.add_argument("docs", nargs="+", help="source doc(s); each needs a <stem>.order.json")
    ap.add_argument("--page", type=int, default=0, help="page to score (0-based, default 0)")
    ap.add_argument("--reading-order", choices=("xycut", "surya"), default="xycut",
                    help="ordering engine to score (default xycut)")
    args = ap.parse_args(argv)

    print(f"{'file':30} {'match':>5} {'tau':>7} {'seq':>7} {'cover':>7}")
    print("-" * 60)
    taus: list[float] = []
    for path in args.docs:
        ref_path = Path(path).with_suffix(".order.json")
        if not ref_path.exists():
            print(f"{Path(path).name[:30]:30} (no .order.json ref)")
            continue
        refs = [tuple(e["bbox"]) for e in json.loads(ref_path.read_text())]
        try:
            hyps = _hyp_boxes(path, args.page, args.reading_order)
        except Exception as e:
            print(f"{Path(path).name[:30]:30} ERROR {type(e).__name__}: {e}")
            continue
        m = reading_order_match(refs, hyps)
        taus.append(m["kendall_tau"])
        print(f"{Path(path).name[:30]:30} {m['matched']:>5} {m['kendall_tau']:>7.3f} "
              f"{m['seq_accuracy']:>7.3f} {m['coverage']:>7.2f}")
    if taus:
        print("-" * 60)
        print(f"{'mean tau':30} {'':>5} {sum(taus) / len(taus):>7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
