# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""PDF paragraph alignment inference from block position (centered titles, right-aligned
runs); the reflow renderer turns it into text-align CSS."""

from __future__ import annotations

from transdoc.extract.pdf import _alignment

W = 600.0


def test_centered_block():
    assert _alignment(220, 380, W) == "center"        # big, ~equal margins


def test_right_aligned_block():
    assert _alignment(450, 580, W) == "right"         # flush right, large left margin


def test_full_width_body_is_left():
    assert _alignment(40, 560, W) is None             # spans the page -> ordinary left


def test_short_left_block_is_left():
    assert _alignment(40, 200, W) is None             # small left margin -> left, not centered


def test_zero_width_safe():
    assert _alignment(0, 100, 0) is None


def test_long_body_paragraph_never_aligned():
    # a long body paragraph in an indented column must stay left, not inherit center/right
    from transdoc.ir import BlockType
    long_text = "x" * 80
    assert _alignment(220, 380, W, text=long_text, btype=BlockType.PARAGRAPH) is None
    assert _alignment(450, 580, W, text=long_text, btype=BlockType.PARAGRAPH) is None


def test_heading_aligned_even_if_longish():
    from transdoc.ir import BlockType
    # a heading still gets centered regardless of length
    assert _alignment(220, 380, W, text="x" * 80, btype=BlockType.HEADING) == "center"
