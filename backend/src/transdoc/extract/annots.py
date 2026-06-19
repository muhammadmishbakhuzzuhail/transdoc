# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Markup annotation capture (highlight / underline / strikeout).

The overlay renderer keeps the original page so its annotations survive untouched. The
reconstruct renderer builds a fresh page and would drop them, so we capture the markup
geometry here and the PDF renderer repaints it. Note + popup text annotations are left to the
overlay path; only the visible text-markup shapes are reproduced in reconstruct.
"""

from __future__ import annotations

# PyMuPDF annotation type numbers for text markup.
_HIGHLIGHT, _UNDERLINE, _SQUIGGLY, _STRIKEOUT = 8, 9, 10, 11
_KIND = {_HIGHLIGHT: "highlight", _UNDERLINE: "underline",
         _SQUIGGLY: "underline", _STRIKEOUT: "strikeout"}


def _hex(stroke) -> str:
    try:
        r, g, b = (int(round(c * 255)) for c in stroke[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return "#ffff00"


def capture(page) -> list[dict]:
    """[{kind, color, quads:[(x0,y0,x1,y1), ...]}] for the text-markup annotations on a page.
    Quads come from the annotation vertices (4 points per marked span) so multi-line markup is
    reproduced line by line. Empty list if the page has none / no annot API."""
    out: list[dict] = []
    try:
        annots = list(page.annots() or [])
    except Exception:
        return out
    for an in annots:
        try:
            kind = _KIND.get(an.type[0])
            if not kind:
                continue
            color = _hex((an.colors or {}).get("stroke") or [1, 1, 0])
            verts = list(getattr(an, "vertices", None) or [])
            quads: list[tuple[float, float, float, float]] = []
            for i in range(0, len(verts) - 3, 4):
                xs = [verts[i + j][0] for j in range(4)]
                ys = [verts[i + j][1] for j in range(4)]
                quads.append((min(xs), min(ys), max(xs), max(ys)))
            if not quads:                      # fall back to the annotation rect
                r = an.rect
                quads = [(r.x0, r.y0, r.x1, r.y1)]
            out.append({"kind": kind, "color": color, "quads": quads})
        except Exception:
            continue
    return out
