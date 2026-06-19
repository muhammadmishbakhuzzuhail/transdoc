# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Terminology-consistency counting logic (no network — translate_fn is injected)."""

from __future__ import annotations

from scripts.eval_consistency import CARRIERS, TERMS, consistency


def test_fully_consistent_scores_one():
    # engine always renders the term as "X" -> canonical "x" appears in every carrier
    def fn(text):
        return text.replace("invoice", "X")
    assert consistency("invoice", CARRIERS, fn) == 1.0


def test_fully_inconsistent_scores_zero():
    # canonical (isolated) rendering never appears in the carrier translations
    calls = {"n": 0}

    def fn(text):
        calls["n"] += 1
        return "AAA" if calls["n"] == 1 else "BBB and CCC"   # canonical 'aaa' absent from carriers

    assert consistency("invoice", CARRIERS, fn) == 0.0


def test_partial_consistency():
    seen = {"i": 0}

    def fn(text):
        # canonical = "term"; half the carriers echo it, half don't
        if text == "invoice":
            return "term"
        seen["i"] += 1
        return "term here" if seen["i"] % 2 == 0 else "other word"

    score = consistency("invoice", CARRIERS, fn)
    assert 0.0 < score < 1.0


def test_terms_and_carriers_present():
    assert "Transdoc" in TERMS and "API" in TERMS   # proper nouns/acronyms weighed highest
    assert all("{t}" in c for c in CARRIERS)
