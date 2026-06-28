# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Render the committed quality time-series (eval/history.jsonl) as a markdown trend table.

    cd backend && .venv/bin/python -m scripts.quality_dashboard            # last 20 runs
    cd backend && .venv/bin/python -m scripts.quality_dashboard --last 50

The history is appended to by the eval/quality scripts (e.g. scripts.eval_translate); this only
reads + renders it, so it needs no network or models.
"""

from __future__ import annotations

import sys

from transdoc.eval.dashboard import load_history, render_markdown


def main(argv: list[str]) -> int:
    last = 20
    if "--last" in argv:
        last = int(argv[argv.index("--last") + 1])
    hist = load_history()
    print("# transdoc quality trend\n")
    print(render_markdown(hist, last=last))
    print(f"\n_{len(hist)} run(s) recorded; reference-free QE / chrF, not a competitor head-to-head._")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
