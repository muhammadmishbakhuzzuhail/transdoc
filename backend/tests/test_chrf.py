"""chrF metric used by the MT quality benchmark (scripts/bench_quality.py)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bench_quality import chrf  # noqa: E402


def test_identical_is_100():
    assert chrf("the quick brown fox", "the quick brown fox") == 100.0


def test_unrelated_is_low():
    assert chrf("the quick brown fox", "zzz xkcd qwerty") < 20


def test_paraphrase_is_mid():
    score = chrf("the quick brown fox", "a fast brown fox")
    assert 30 < score < 80


def test_empty_safe():
    assert chrf("", "") == 0.0
    assert chrf("hello", "") == 0.0
