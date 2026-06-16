"""Block-typing accuracy eval (Area D, D2).

eval_layout scores the layout MODEL's region labels; this scores the FINAL IR block types after the
whole extract path (heuristic typing + PP-StructureV3 labels + the D2 running-head/footer/page-
number pass). For each doc with a `<stem>.types.json` reference (blocks' type + bbox), it extracts
via the pipeline and reports overall type accuracy, per-type precision/recall, and the confusion
pairs — so a 'footer typed as paragraph' regression is visible.

Reference sidecar — one JSON per doc (page-0 by default; --page for another):

    [{"type": "header", "bbox": [x0, y0, x1, y1]}, {"type": "paragraph", "bbox": [..]}, ...]

types are the BlockType values (title/heading/paragraph/footnote/header/footer/page_number/...).
BYO refs, deterministic (extraction only), opt-in.

    cd backend && .venv/bin/python -m scripts.eval_typing path/to/doc.pdf [more docs...]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _hyp(path: str, page: int):
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    doc = extract(detect(path), Config(target_lang="id"))
    return [(b.type.value, (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1))
            for b in doc.ordered_blocks() if b.page == page and b.bbox]


def main(argv: list[str]) -> int:
    from transdoc.eval.metrics import typing_match

    ap = argparse.ArgumentParser(description="block-typing accuracy eval (Area D)")
    ap.add_argument("docs", nargs="+", help="source doc(s); each needs a <stem>.types.json")
    ap.add_argument("--page", type=int, default=0, help="page to score (0-based, default 0)")
    ap.add_argument("--show", action="store_true", help="print per-type P/R + confusion")
    args = ap.parse_args(argv)

    print(f"{'file':30} {'match':>5} {'acc':>7}")
    print("-" * 46)
    accs: list[float] = []
    for path in args.docs:
        ref_path = Path(path).with_suffix(".types.json")
        if not ref_path.exists():
            print(f"{Path(path).name[:30]:30} (no .types.json ref)")
            continue
        refs = [(e["type"], tuple(e["bbox"])) for e in json.loads(ref_path.read_text())]
        try:
            hyps = _hyp(path, args.page)
        except Exception as e:
            print(f"{Path(path).name[:30]:30} ERROR {type(e).__name__}: {e}")
            continue
        m = typing_match(refs, hyps)
        accs.append(m["accuracy"])
        print(f"{Path(path).name[:30]:30} {m['matched']:>5} {m['accuracy']:>7.3f}")
        if args.show:
            for t, s in m["per_type"].items():
                if s["refs"] or s["hyps"]:
                    print(f"    {t:14} P={s['precision']:.2f} R={s['recall']:.2f} "
                          f"(tp={s['tp']} ref={s['refs']} hyp={s['hyps']})")
            for rt, ht in m["confusion"]:
                print(f"    confused {rt} -> {ht}")
    if accs:
        print("-" * 46)
        print(f"{'mean acc':30} {'':>5} {sum(accs) / len(accs):>7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
