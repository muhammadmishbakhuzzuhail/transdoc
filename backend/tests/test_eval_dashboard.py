# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Quality time-series dashboard: append/load round-trip + markdown render with deltas."""

from __future__ import annotations

from transdoc.eval.dashboard import append_history, load_history, render_markdown


def test_append_load_roundtrip(tmp_path):
    p = tmp_path / "history.jsonl"
    assert load_history(p) == []                       # missing file -> empty
    append_history({"date": "2026-01-01", "kind": "flores", "metric": "chrf", "overall": 50.0}, p)
    append_history({"date": "2026-01-02", "kind": "flores", "metric": "chrf", "overall": 52.0}, p)
    hist = load_history(p)
    assert [r["overall"] for r in hist] == [50.0, 52.0]


def test_render_markdown_shows_delta_vs_prior_same_series():
    hist = [
        {"date": "2026-01-01", "kind": "flores", "metric": "chrf", "overall": 50.0, "n": 50},
        {"date": "2026-01-02", "kind": "flores", "metric": "chrf", "overall": 52.5, "n": 50},
    ]
    md = render_markdown(hist)
    assert "52.5" in md
    assert "+2.5" in md            # delta vs the prior run of the same (kind, metric)


def test_render_markdown_empty():
    assert "no quality runs" in render_markdown([])
