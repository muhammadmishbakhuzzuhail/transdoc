# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Quality time-series: a committed JSONL history of eval/quality runs + a markdown trend render.

The eval gate answers "did anything regress vs the last baseline?" — one bit. This keeps the
*trend*: each run appends one timestamped record (engine, metric, per-pair/per-doc scores) to a
JSONL history, so quality over time is visible and the last-known numbers live in the repo rather
than only in a private notebook. Pure functions (append/load/render) so they're offline-testable;
the CLI is scripts/quality_dashboard.py.

Record shape (free-form, these keys are conventional):
  {"date": "2026-06-25", "engine": "google", "kind": "validate",
   "metric": "comet_qe", "overall": 0.74, "scores": {"hindi": 0.779, ...}, "note": "..."}
"""

from __future__ import annotations

import json
from pathlib import Path

HISTORY_PATH = Path(__file__).parent / "history.jsonl"


def append_history(record: dict, path: str | Path = HISTORY_PATH) -> None:
    """Append one record as a JSONL line (creating the file/parents if needed)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def load_history(path: str | Path = HISTORY_PATH) -> list[dict]:
    """Load all records, oldest first; missing file = empty history."""
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def render_markdown(history: list[dict], last: int = 20) -> str:
    """Render the most recent `last` runs as a markdown table with the delta vs the prior run of
    the same (kind, metric). Empty history -> a friendly placeholder."""
    if not history:
        return "_no quality runs recorded yet_"
    rows = history[-last:]
    prev: dict[tuple, float] = {}
    out = ["| date | kind | engine | metric | overall | Δ | n |",
           "|------|------|--------|--------|--------:|--:|--:|"]
    # walk the WHOLE history to compute deltas correctly, but only print the tail
    cutoff = len(history) - len(rows)
    for i, r in enumerate(history):
        key = (r.get("kind", ""), r.get("metric", ""))
        overall = r.get("overall")
        delta = ""
        if overall is not None and key in prev:
            d = overall - prev[key]
            delta = f"{d:+.3f}" if abs(d) < 1 else f"{d:+.1f}"
        if overall is not None:
            prev[key] = overall
        if i >= cutoff:
            ov = f"{overall:.3f}" if isinstance(overall, float) and abs(overall) < 1 else str(overall)
            n = r.get("n", len(r.get("scores", {})) or "")
            out.append(f"| {r.get('date','')} | {r.get('kind','')} | {r.get('engine','')} "
                       f"| {r.get('metric','')} | {ov} | {delta} | {n} |")
    return "\n".join(out)
