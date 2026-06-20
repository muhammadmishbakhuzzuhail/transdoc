# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Text normalization for extracted content — de-hyphenation, ligature folding, Unicode NFC.

Research-driven (deep-research 2026-06-15): PyMuPDF's `dehyphenate` flag is OFF for all
text/dict/words extraction (only ON for search), so a word split across a line break stays
"inter-\\nnational"; and PyMuPDF only decomposes the 7 standard Latin ligatures. Broken words
and ligatures degrade both display fidelity and translation quality (the MT engine mistranslates
"inter national" or "ﬁle"). This pass cleans extracted block/cell text conservatively.

Conservative on purpose:
- NFC (canonical) — NOT NFKC, which would rewrite ½, ², etc.
- de-hyphenate only a hyphen/soft-hyphen at a LINE BREAK between two letters (the unambiguous
  case); a real hyphenated compound mid-line ("well-known") has no newline and is untouched.
- strip soft hyphen / zero-width space / BOM; keep ZWNJ/ZWJ (meaningful in Arabic/Indic).
- fold the Latin presentation ligatures PyMuPDF leaves intact.
"""

from __future__ import annotations

import re
import unicodedata

_LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "ft", "ﬆ": "st",
}
_LIG_RE = re.compile("[" + "".join(_LIGATURES) + "]")
_STRIP = str.maketrans("", "", "­​﻿")   # soft hyphen, ZWSP, BOM
# letter + (hyphen | soft hyphen) + (newline | spaces) + letter  ->  join (drop hyphen + break).
# Newline case allows any following letter (classic "inter-\nnational"). The SPACE case matters
# because blocks are space-joined long before this runs — so on the OCR/structured/PDF paths the
# newline is already gone and "inter- national" would otherwise reach the translator. It requires
# a LOWERCASE letter after, leaving a real compound/sentence break ("well- Known") and ranges
# ("10 - 20", digits) intact.
_DEHYPHEN = re.compile(r"(?<=[^\W\d_])[-­](?:\n(?=[^\W\d_])|[ \t]+(?=[a-z]))")

# CJK PDFs frequently extract with a space between every glyph ("联 合 国 大 会"), an artifact of
# per-glyph positioning in the content stream. Real CJK has no inter-character spaces, and those
# stray spaces shatter the text for the MT engine — measured: NMT collapses into a repetition loop
# ("one person, one person, …") on spaced Chinese. Collapse spaces/tabs sitting BETWEEN two CJK
# characters (Han, kana, Hangul, CJK punctuation). Digit/Latin boundaries are left alone (a digit
# anchors a number, e.g. "1948 年"), so this is safe for mixed text.
_CJK = ("　-〿぀-ヿㇰ-ㇿ㐀-䶿一-鿿"
        "豈-﫿가-힯＀-￯")
_CJK_SPACE = re.compile(rf"(?<=[{_CJK}])[ \t]+(?=[{_CJK}0-9])|(?<=[0-9])[ \t]+(?=[{_CJK}])")


def clean(text: str) -> str:
    if not text:
        return text
    text = unicodedata.normalize("NFC", text)
    text = _DEHYPHEN.sub("", text)                       # join line-break hyphenation first
    text = text.translate(_STRIP)                        # then drop stray soft hyphens / ZWSP
    text = _LIG_RE.sub(lambda m: _LIGATURES[m.group()], text)
    text = _CJK_SPACE.sub("", text)                      # de-space per-glyph CJK extraction
    return text


def normalize_doc(doc) -> None:
    """Apply clean() to every block's text and every table cell, in place."""
    for b in doc.blocks:
        if b.text:
            b.text = clean(b.text)
        for r in b.runs:
            if r.text:
                r.text = clean(r.text)
        if b.table:
            for row in b.table.rows:
                for c in row:
                    if c.text:
                        c.text = clean(c.text)
