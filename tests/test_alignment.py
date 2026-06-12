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
