# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Translation-quality regression gate (DeepL-style metrics tracking).

Translates a small committed held-out set (quality_set.json) through the real engine and scores it
with chrF against the references, then compares to a committed baseline — so a translation-quality
regression is caught, not just a structural one. Needs network (the engine is online), so it runs
as a SEPARATE nightly/manual CI job, never blocking a PR on a flaky request.

The scoring + regression check are pure functions (testable offline); the CLI in
``scripts/quality_gate.py`` wires the real engine.
"""

from __future__ import annotations

import json
from pathlib import Path

SET_PATH = Path(__file__).parent / "quality_set.json"
BASELINE_PATH = Path(__file__).parent / "quality_baseline.json"
DEFAULT_TOL = 2.0           # chrF points a pair may drop before it counts as a regression


def load_set(path: str | Path = SET_PATH) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _pair(item: dict) -> str:
    return f"{item['src_lang']}-{item['tgt_lang']}"


def score_set(items: list[dict], translate) -> dict:
    """Score the set. ``translate(srcs, src_lang, tgt_lang) -> list[str]`` does the engine call
    (injected so tests can stub it). Returns {"pairs": {pair: meanChrF}, "overall": meanChrF,
    "n": count}."""
    from .metrics import chrf

    by_pair: dict[str, list[dict]] = {}
    for it in items:
        by_pair.setdefault(_pair(it), []).append(it)
    pair_scores: dict[str, float] = {}
    all_scores: list[float] = []
    for pair, group in by_pair.items():
        sl, tl = group[0]["src_lang"], group[0]["tgt_lang"]
        hyps = translate([g["src"] for g in group], sl, tl)
        scores = [chrf(g["ref"], h) for g, h in zip(group, hyps)]
        pair_scores[pair] = round(sum(scores) / len(scores), 2) if scores else 0.0
        all_scores += scores
    overall = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0.0
    return {"pairs": pair_scores, "overall": overall, "n": len(items)}


def check_regression(current: dict, baseline: dict, tol: float = DEFAULT_TOL) -> list[str]:
    """Return human-readable regression messages where a pair's (or the overall) chrF dropped more
    than ``tol`` below the baseline. Empty list = no regression."""
    out = []
    base_pairs = baseline.get("pairs", {})
    for pair, base in base_pairs.items():
        cur = current.get("pairs", {}).get(pair)
        if cur is None:
            out.append(f"{pair}: missing in current run (baseline {base})")
        elif cur < base - tol:
            out.append(f"{pair}: {cur} < {base} - {tol} (regressed {base - cur:.2f})")
    b_overall = baseline.get("overall")
    if b_overall is not None and current.get("overall", 0) < b_overall - tol:
        out.append(f"overall: {current['overall']} < {b_overall} - {tol}")
    return out
