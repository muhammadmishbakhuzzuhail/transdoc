# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Formula detection: equation lines are typed FORMULA (preserved verbatim), prose is not.

Guards the academic-PDF case where translating `head_i = Attention(...)` scrambled the
math into `head; = Perhatian(...)`."""

from __future__ import annotations

from transdoc.extract.pdf import _looks_formula


def test_equations_detected():
    assert _looks_formula("MultiHead(Q, K, V) = Concat(head1, ..., headh)W O")
    assert _looks_formula("where headi = Attention(QW Q i , KW K i , V W V i )")
    assert _looks_formula("FFN(x) = max(0, xW1 + b1)W2 + b2 (2)")
    assert _looks_formula("E = mc2 where c ∈ R")


def test_prose_not_detected():
    # inline math in a sentence must stay translatable
    assert not _looks_formula("In this work we employ h = 8 parallel attention layers.")
    assert not _looks_formula(
        "Where the projections are parameter matrices and W maps to the model dimension.")
    assert not _looks_formula("The Transformer uses multi-head attention in three ways:")
    assert not _looks_formula("3.2.3 Applications of Attention in our Model")
    assert not _looks_formula("")
