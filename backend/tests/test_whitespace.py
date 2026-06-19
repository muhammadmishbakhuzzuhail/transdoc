# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Whitespace fidelity on the part we control — extraction. The normalizer must NOT collapse
non-breaking spaces, tabs, or runs of spaces (only de-hyphenate line breaks + fold ligatures +
strip zero-width). Inter-word spacing in the translated output is the MT engine's to decide."""

from __future__ import annotations

from transdoc.extract.textnorm import clean


def test_nbsp_preserved():
    assert " " in clean("5 km")


def test_tab_preserved():
    assert "\t" in clean("name\tvalue")


def test_multiple_spaces_not_collapsed():
    assert "two  spaces" in clean("two  spaces")


def test_zero_width_still_stripped():
    # ZWSP / soft hyphen still go (that is the documented cleanup), nbsp stays
    out = clean("a​b c")
    assert "​" not in out and " " in out
