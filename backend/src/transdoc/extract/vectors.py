# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Vector line-art capture (PyMuPDF get_drawings) -> simple IR primitives.

The reconstruct renderer rebuilds a fresh page from text + image crops, so without this it
drops every rule line, divider, field underline and box. We capture lines and rectangles
(the shapes that carry document structure) with their stroke colour/width and fill, so the
renderer can redraw them at the original positions. Curves/beziers are rare in documents and
skipped. Coordinates are PDF points, matching the digital text bboxes.
"""

from __future__ import annotations

# Ignore hairline noise and full-page background rectangles (handled as page bg, not line-art).
_MIN_LEN = 3.0


def _rgb(c) -> str | None:
    if not c:
        return None
    try:
        r, g, b = (max(0, min(255, round(v * 255))) for v in c[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def capture(page) -> list[dict]:
    """Return [{kind:'line', x0,y0,x1,y1, color, width}, {kind:'rect', x0,y0,x1,y1, color,
    width, fill}] for a page, in PDF points. Empty list if PyMuPDF has no drawings API."""
    try:
        drawings = page.get_drawings()
    except Exception:
        return []
    out: list[dict] = []
    pw, ph = page.rect.width, page.rect.height
    for d in drawings:
        color = _rgb(d.get("color"))
        fill = _rgb(d.get("fill"))
        width = float(d.get("width") or 0.0) or 0.6
        # dash pattern, e.g. "[3 2] 0" for a dashed/dotted stroke; "[] 0" / None = solid
        dash = d.get("dashes")
        dash = dash if (dash and dash != "[] 0") else None
        for item in d.get("items", []):
            op = item[0]
            if op == "l":                      # line: (p1, p2)
                p1, p2 = item[1], item[2]
                if abs(p2.x - p1.x) + abs(p2.y - p1.y) < _MIN_LEN:
                    continue
                out.append({"kind": "line", "x0": p1.x, "y0": p1.y, "x1": p2.x, "y1": p2.y,
                            "color": color or "#000000", "width": width, "dashes": dash})
            elif op == "c":                    # cubic bezier curve: (p1, p2, p3, p4)
                try:
                    pts = [(p.x, p.y) for p in item[1:5]]
                except Exception:
                    continue
                out.append({"kind": "curve", "points": pts,
                            "color": color or "#000000", "width": width})
            elif op == "re":                   # rectangle
                r = item[1]
                if r.width < _MIN_LEN and r.height < _MIN_LEN:
                    continue
                # a near-full-page rect is a background panel, not line-art
                if r.width >= pw * 0.95 and r.height >= ph * 0.95:
                    continue
                out.append({"kind": "rect", "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
                            "color": color, "width": width, "fill": fill, "dashes": dash})
    return out


def page_background(page) -> str | None:
    """Hex fill of a near-full-page background panel, if the page has one (a coloured page,
    not white). These are skipped by capture() as line-art; reconstruct paints this first so a
    coloured page survives. None when the page is plain white."""
    try:
        drawings = page.get_drawings()
    except Exception:
        return None
    pw, ph = page.rect.width, page.rect.height
    best = None
    for d in drawings:
        fill = _rgb(d.get("fill"))
        if not fill or fill.lower() in ("#ffffff", "#fff"):
            continue
        for item in d.get("items", []):
            if item[0] != "re":
                continue
            r = item[1]
            if r.width >= pw * 0.95 and r.height >= ph * 0.95:
                best = fill        # last (top-most) full-page fill wins
    return best
