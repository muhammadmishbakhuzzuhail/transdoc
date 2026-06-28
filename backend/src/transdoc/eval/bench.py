# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Head-to-head engine benchmark — the matrix behind any 'more accurate' claim.

Translate the same FLORES-200 source through several engines and score each against the FLORES
gold reference, per language pair. This is the FREE head-to-head: it compares the engines we can
run ourselves (the online endpoint + the offline NMT models) on a public benchmark with gold
references — no paid DeepL/Google-Cloud API needed. The point it proves is the thesis behind
QE-gated engine selection: different engines win different language pairs, so picking per pair
beats fixing one engine.

Pure builder here (injectable translate/metric deps, offline-testable); scripts/bench_vs_engines.py
wires the real engines, sacrebleu, and reference-based COMET, and is run manually on GPU.
"""

from __future__ import annotations


def score_matrix(langs, engines, src_by_lang, ref_by_lang, translate_fn, metric_fns):
    """Return {lang: {engine: {metric: value} | {"error": str}}}.

    translate_fn(engine, lang, srcs) -> hyps (list aligned with srcs).
    metric_fns = {metric_name: fn(refs, hyps) -> float | None}.
    A failing engine/lang cell records {"error": "..."} rather than aborting the whole run."""
    matrix: dict = {}
    for lang in langs:
        srcs, refs = src_by_lang[lang], ref_by_lang[lang]
        row: dict = {}
        for eng in engines:
            try:
                hyps = translate_fn(eng, lang, srcs)
            except Exception as e:
                row[eng] = {"error": f"{type(e).__name__}: {e}"}
                continue
            cell = {}
            for name, fn in metric_fns.items():
                val = fn(refs, hyps)
                if val is not None:
                    cell[name] = round(val, 2)
            row[eng] = cell
        matrix[lang] = row
    return matrix


def best_per_lang(matrix, metric):
    """{lang: winning_engine} by the given metric (higher = better). Cells without the metric or
    with an error are ignored; a lang with no scorable cell is omitted."""
    out = {}
    for lang, row in matrix.items():
        scored = {e: c[metric] for e, c in row.items() if isinstance(c, dict) and metric in c}
        if scored:
            out[lang] = max(scored, key=lambda e: scored[e])
    return out


def render_markdown(matrix, engines, metric="chrf"):
    """Render the matrix as a markdown table (langs × engines) for one metric, bolding the winner
    per row and noting which engine wins each pair underneath."""
    head = "| lang | " + " | ".join(engines) + " |"
    sep = "|------|" + "|".join(["---:"] * len(engines)) + "|"
    lines = [head, sep]
    winners = best_per_lang(matrix, metric)
    for lang, row in matrix.items():
        cells = []
        for e in engines:
            c = row.get(e, {})
            if "error" in c:
                cells.append("err")
            elif metric in c:
                v = f"{c[metric]:.1f}"
                cells.append(f"**{v}**" if winners.get(lang) == e else v)
            else:
                cells.append("-")
        lines.append(f"| {lang} | " + " | ".join(cells) + " |")
    if winners:
        tally: dict[str, int] = {}
        for e in winners.values():
            tally[e] = tally.get(e, 0) + 1
        won = ", ".join(f"{e} ({n})" for e, n in sorted(tally.items(), key=lambda kv: -kv[1]))
        lines.append("")
        lines.append(f"_Pairs won by {metric}: {won}_")
    return "\n".join(lines)
