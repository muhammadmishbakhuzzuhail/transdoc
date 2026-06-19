# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Translation-quality regression gate CLI (Area: DeepL-style metrics).

Translates the committed held-out set through the real engine, scores chrF, and compares to the
committed baseline — exits non-zero on a regression. Online (the engine is online); runs as a
nightly/manual CI job, not on every PR.

    cd backend && .venv/bin/python -m scripts.quality_gate                 # check vs baseline
    cd backend && .venv/bin/python -m scripts.quality_gate --engine google
    cd backend && .venv/bin/python -m scripts.quality_gate --update        # write a new baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    from transdoc.config import Config, Engine
    from transdoc.eval.quality_gate import (
        BASELINE_PATH, DEFAULT_TOL, check_regression, load_set, score_set,
    )
    from transdoc.translate import get_translator

    ap = argparse.ArgumentParser(description="translation-quality regression gate (chrF)")
    ap.add_argument("--engine", default="google")
    ap.add_argument("--tol", type=float, default=DEFAULT_TOL)
    ap.add_argument("--update", action="store_true", help="write current scores as the new baseline")
    args = ap.parse_args(argv)

    def translate(srcs, src_lang, tgt_lang):
        cfg = Config(source_lang=src_lang, target_lang=tgt_lang, engine=Engine(args.engine))
        return get_translator(cfg).translate_batch(srcs, cfg, src=src_lang)

    try:
        current = score_set(load_set(), translate)
    except Exception as e:
        sys.stderr.write(f"quality run failed ({type(e).__name__}: {e})\n")
        return 1

    print(f"chrF (engine={args.engine}, n={current['n']})")
    for pair, sc in sorted(current["pairs"].items()):
        print(f"  {pair:10} {sc:6.2f}")
    print(f"  {'overall':10} {current['overall']:6.2f}")

    if args.update:
        Path(BASELINE_PATH).write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote baseline -> {BASELINE_PATH}")
        return 0

    if not Path(BASELINE_PATH).exists():
        sys.stderr.write("\nno baseline yet — run with --update to create one\n")
        return 0
    baseline = json.loads(Path(BASELINE_PATH).read_text())
    regressions = check_regression(current, baseline, args.tol)
    if regressions:
        print("\nREGRESSION:")
        for r in regressions:
            print(f"  {r}")
        return 1
    print(f"\nno regression vs baseline (tol {args.tol} chrF)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
