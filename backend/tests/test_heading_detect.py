# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Heading detection beyond the font-size ratio: numbered sections and short bold lines are
headings; bold author bylines (with an email) and ordinary sentences are not."""

from __future__ import annotations

from transdoc.extract.pdf import _guess_type
from transdoc.ir import BlockType

BODY = 10.0


def test_font_size_headings():
    assert _guess_type(17.0, BODY) == BlockType.TITLE       # >=1.6x
    assert _guess_type(13.0, BODY) == BlockType.HEADING     # >=1.2x


def test_numbered_section_is_heading():
    assert _guess_type(BODY, BODY, bold=False, text="3.2 Attention") == BlockType.HEADING
    assert _guess_type(BODY, BODY, bold=False, text="1 Introduction") == BlockType.HEADING


def test_short_bold_line_is_heading():
    assert _guess_type(BODY, BODY, bold=True, text="Abstract") == BlockType.HEADING


def test_author_byline_is_not_heading():
    # bold and short, but carries an email -> a byline, not a heading
    t = "Ashish Vaswani Google Brain avaswani@google.com"
    assert _guess_type(BODY, BODY, bold=True, text=t) == BlockType.PARAGRAPH


def test_plain_sentence_is_paragraph():
    t = "This is an ordinary body sentence."
    assert _guess_type(BODY, BODY, bold=False, text=t) == BlockType.PARAGRAPH
