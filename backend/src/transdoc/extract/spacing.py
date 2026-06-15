"""Glyph-gap word spacing (the deferred research item "F").

Some PDFs encode text whose space glyphs are missing or whose kerning collapses inter-word gaps,
so `get_text` returns "twowords" stuck together. PyMuPDF's per-glyph geometry (`get_text(
"rawdict")`) still has the true x-positions, so a wide horizontal gap between two glyphs with no
space character between them is a missing word break.

This is conservative on purpose (the research found 0 symptoms in an 8-PDF corpus, so the risk is
false insertions): a space is added only at a gap clearly wider than the line's own median glyph
advance, and the caller only adopts the result when it differs from the plain extraction *purely
by added whitespace* (same non-space characters) — so a divergent re-assembly can never corrupt
text, it is simply ignored.
"""

from __future__ import annotations

import re
import statistics

_ALNUM = re.compile(r"\s+")


def _gap_factor() -> float:
    # gap > this * median glyph width => a word break. Word spaces are ~one glyph-advance wide;
    # intra-word gaps are near zero, so 0.4 sits well clear of both.
    return 0.4


def line_join(chars: list[dict]) -> str:
    """Join one text line's glyphs (each {'c', 'bbox'=(x0,y0,x1,y1)}) left-to-right, inserting a
    space at any gap wider than 0.4x the line's median glyph width when no space is present."""
    glyphs = sorted((c for c in chars if c.get("c")), key=lambda c: c["bbox"][0])
    if not glyphs:
        return ""
    widths = [c["bbox"][2] - c["bbox"][0] for c in glyphs if c["c"].strip()]
    med = statistics.median(widths) if widths else 0.0
    out: list[str] = []
    prev = None
    for c in glyphs:
        ch = c["c"]
        if prev is not None and med > 0:
            gap = c["bbox"][0] - prev["bbox"][2]
            if (gap > _gap_factor() * med and ch != " " and prev["c"] != " "
                    and (not out or out[-1] != " ")):
                out.append(" ")
        out.append(ch)
        prev = c
    return "".join(out)


def text_in_bbox(raw_blocks: list[dict], bbox) -> str:
    """Re-assemble the text inside a block bbox from rawdict glyphs, line by line, applying
    gap-based word spacing. Lines are joined with a single space. Empty string if no glyphs."""
    x0, y0, x1, y1 = bbox
    lines_out: list[str] = []
    for blk in raw_blocks:
        for line in blk.get("lines", []):
            chars = [c for span in line.get("spans", []) for c in span.get("chars", [])]
            inside = [c for c in chars
                      if x0 - 1 <= (c["bbox"][0] + c["bbox"][2]) / 2 <= x1 + 1
                      and y0 - 1 <= (c["bbox"][1] + c["bbox"][3]) / 2 <= y1 + 1]
            joined = line_join(inside)
            if joined.strip():
                lines_out.append(joined)
    return " ".join(lines_out)


def merge_if_only_spacing(plain: str, spaced: str) -> str:
    """Adopt `spaced` only if it is `plain` with extra spaces (identical once whitespace is
    removed) AND it actually added some. Otherwise keep `plain` — never risk corrupting text."""
    if not spaced:
        return plain
    if _ALNUM.sub("", plain) != _ALNUM.sub("", spaced):
        return plain
    if spaced.count(" ") <= plain.count(" "):
        return plain
    return spaced
