# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Layout region-accuracy eval (IoU + detection P/R/F1 + label accuracy).

Counts say "5 regions"; they can't say whether those regions are in the RIGHT PLACES with the
RIGHT TYPES. A 40pt drift makes overlay-redaction blank the wrong area and reconstruct place text
offset — invisible to every count-based gate. This scores layout geometry: greedy-match the
extracted regions to a reference by IoU and report mean IoU of matched boxes, detection
precision/recall/F1 at IoU>=0.5, and the label accuracy of matched pairs.

Reference sidecar `<stem>.layout.json` — one JSON file per doc:

    [{"label": "title", "bbox": [x0, y0, x1, y1]},
     {"label": "paragraph", "bbox": [...]}, ...]

bbox in PDF points, page 1. Labels are IR block types (title/heading/paragraph/table/figure/
caption/formula/list_item). Bring your own references (not committed). Deterministic (echo);
local/opt-in.

    cd backend && .venv/bin/python -m scripts.eval_layout path/to/doc.pdf [more docs...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _doc_regions(path: str):
    """Extract the doc; return page-1 (label, bbox-tuple) regions in reading order."""
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    doc = extract(detect(path), Config(target_lang="id"))
    out = []
    for b in sorted(doc.blocks, key=lambda b: (b.page, b.reading_order)):
        if b.page > 0:
            break               # page 1 only (matches the reference sidecar)
        if b.bbox is not None:
            out.append((b.type.value, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)))
    return out


def _ref_regions(sidecar: Path):
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    return [(d["label"], tuple(d["bbox"])) for d in data]


def main(argv: list[str]) -> int:
    from transdoc.eval.metrics import layout_match

    if not argv:
        sys.stderr.write("usage: eval_layout <doc> [<doc> ...]  (each needs a <stem>.layout.json)\n")
        return 2
    print(f"{'file':28} {'IoU':>6} {'P':>6} {'R':>6} {'F1':>6} {'label':>6}")
    print("-" * 62)
    agg: list[dict] = []
    for path in argv:
        sidecar = Path(path).with_suffix(".layout.json")
        if not sidecar.exists():
            print(f"{Path(path).name[:28]:28} {'(no .layout.json ref)':>20}")
            continue
        try:
            m = layout_match(_ref_regions(sidecar), _doc_regions(path))
        except Exception as e:
            print(f"{Path(path).name[:28]:28} ERROR {type(e).__name__}: {e}")
            continue
        agg.append(m)
        print(f"{Path(path).name[:28]:28} {m['mean_iou']:>6.2f} {m['precision']:>6.2f} "
              f"{m['recall']:>6.2f} {m['f1']:>6.2f} {m['label_acc']:>6.2f}")
    if agg:
        print("-" * 62)
        n = len(agg)
        print(f"{'mean':28} {sum(m['mean_iou'] for m in agg) / n:>6.2f} "
              f"{sum(m['precision'] for m in agg) / n:>6.2f} "
              f"{sum(m['recall'] for m in agg) / n:>6.2f} "
              f"{sum(m['f1'] for m in agg) / n:>6.2f} "
              f"{sum(m['label_acc'] for m in agg) / n:>6.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
