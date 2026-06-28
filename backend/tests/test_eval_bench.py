# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Head-to-head benchmark matrix: build / pick-winner / render, all offline (stub deps)."""

from __future__ import annotations

from transdoc.eval.bench import best_per_lang, render_markdown, score_matrix

# de: opusmt best; hi: nllb best — the per-pair-winner story
_CHRF = {
    ("de", "google"): 55.0, ("de", "opusmt"): 62.0, ("de", "nllb"): 50.0,
    ("hi", "google"): 48.0, ("hi", "opusmt"): 30.0, ("hi", "nllb"): 53.0,
}


def _matrix():
    langs, engines = ["de", "hi"], ["google", "opusmt", "nllb"]
    src = {lg: ["s1", "s2"] for lg in langs}
    ref = {lg: ["r1", "r2"] for lg in langs}

    def translate_fn(engine, lang, texts):
        if engine == "broken":
            raise RuntimeError("boom")
        return [f"{engine}:{lang}:{t}" for t in texts]

    metric_fns = {"chrf": lambda refs, hyps: _CHRF[(hyps[0].split(":")[1], hyps[0].split(":")[0])]}
    return score_matrix(langs, engines, src, ref, translate_fn, metric_fns), langs, engines


def test_score_matrix_and_winners():
    matrix, langs, engines = _matrix()
    assert matrix["de"]["opusmt"]["chrf"] == 62.0
    winners = best_per_lang(matrix, "chrf")
    assert winners == {"de": "opusmt", "hi": "nllb"}     # different engines win different pairs


def test_render_bolds_winner_and_tallies():
    matrix, langs, engines = _matrix()
    md = render_markdown(matrix, engines, metric="chrf")
    assert "**62.0**" in md            # de winner bolded
    assert "**53.0**" in md            # hi winner bolded
    assert "opusmt (1)" in md and "nllb (1)" in md


def test_engine_error_cell_is_isolated():
    langs, engines = ["de"], ["google", "broken"]
    src = {"de": ["s1"]}
    ref = {"de": ["r1"]}

    def translate_fn(engine, lang, texts):
        if engine == "broken":
            raise RuntimeError("boom")
        return ["x"]

    matrix = score_matrix(langs, engines, src, ref, translate_fn, {"chrf": lambda r, h: 40.0})
    assert matrix["de"]["google"]["chrf"] == 40.0
    assert "error" in matrix["de"]["broken"]
    # render shows 'err' for the failed cell, doesn't crash
    assert "err" in render_markdown(matrix, engines, metric="chrf")
