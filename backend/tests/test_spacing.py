# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Glyph-gap word spacing (research item F): pure join logic + the safety merge."""

from __future__ import annotations

from transdoc.extract.spacing import line_join, merge_if_only_spacing, text_in_bbox


def _ch(c, x0, x1, y0=0.0, y1=10.0):
    return {"c": c, "bbox": (x0, y0, x1, y1)}


def test_line_join_inserts_space_at_wide_gap():
    # two 5-wide glyphs touching, then a 6-unit gap, then two more -> one space inserted
    chars = [_ch("h", 0, 5), _ch("i", 5, 10), _ch("t", 16, 21), _ch("o", 21, 26)]
    assert line_join(chars) == "hi to"


def test_line_join_no_space_within_word():
    chars = [_ch("w", 0, 5), _ch("o", 5, 10), _ch("r", 10, 15), _ch("d", 15, 20)]
    assert line_join(chars) == "word"


def test_line_join_keeps_existing_space():
    chars = [_ch("a", 0, 5), _ch(" ", 5, 8), _ch("b", 8, 13)]
    assert line_join(chars) == "a b"


def test_merge_adopts_only_added_spaces():
    assert merge_if_only_spacing("twowords", "two words") == "two words"


def test_merge_rejects_divergent_text():
    # different non-space characters -> keep the plain text, never corrupt
    assert merge_if_only_spacing("twowords", "two werds") == "twowords"


def test_merge_rejects_when_no_new_space():
    assert merge_if_only_spacing("already fine", "already fine") == "already fine"


def test_text_in_bbox_groups_lines():
    raw = [{"lines": [
        {"spans": [{"chars": [_ch("h", 0, 5, 0, 10), _ch("i", 16, 21, 0, 10)]}]},
        {"spans": [{"chars": [_ch("y", 0, 5, 20, 30), _ch("o", 5, 10, 20, 30)]}]},
    ]}]
    out = text_in_bbox(raw, (0, 0, 100, 100))
    assert out == "h i yo"
