"""Cross-source region reconciliation for the IR.

The structured extractor fuses several sources onto one page — PP-StructureV3 regions (labels,
tables, formulas, figures), the PyMuPDF digital text layer (the words + style), and figure
boxes merged from layout detection. They overlap, so the IR needs a reconcile pass:

  1. Drop a TEXT block that sits mostly inside a non-text region (figure / formula / table).
     That text is already carried by the region's verbatim crop or cell grid; keeping it would
     double the content AND draw words on top of the figure crop (the "overwrite" defect the
     fidelity audit flags).
  2. Drop a TEXT block whose text duplicates (or is contained in) another's — keep the longer,
     more complete one (PP-StructureV3 sometimes returns overlapping text regions).

Non-text blocks (figures/formulas/tables) are never dropped.
"""

from __future__ import annotations

from ..ir import Block, BlockType

_NONTEXT = {BlockType.FIGURE, BlockType.FORMULA, BlockType.TABLE}
_TEXT = {BlockType.PARAGRAPH, BlockType.HEADING, BlockType.TITLE, BlockType.CAPTION,
         BlockType.LIST_ITEM}


def _area(b) -> float:
    return max(0.0, b.x1 - b.x0) * max(0.0, b.y1 - b.y0)


def _contained(inner, outer, frac: float = 0.7) -> bool:
    """True if `frac` of `inner`'s area lies inside `outer`."""
    ix0, iy0 = max(inner.x0, outer.x0), max(inner.y0, outer.y0)
    ix1, iy1 = min(inner.x1, outer.x1), min(inner.y1, outer.y1)
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    a = _area(inner)
    return a > 0 and inter / a >= frac


def _norm(s: str) -> str:
    return " ".join((s or "").lower().split())


def _dedup_text(blocks: list[Block]) -> list[Block]:
    """Drop a text block whose normalized text duplicates (or is contained in) another's; keep
    the longer. Non-text blocks pass through untouched."""
    kept: list[Block] = []
    norms: list[str] = []
    for b in blocks:
        if b.type not in _TEXT or len(_norm(b.text)) < 15:
            kept.append(b)
            norms.append("")
            continue
        n = _norm(b.text)
        dup_at = -1
        for i, kn in enumerate(norms):
            if not kn:
                continue
            if n == kn or (len(n) > 20 and n in kn) or (len(kn) > 20 and kn in n):
                dup_at = i
                break
        if dup_at == -1:
            kept.append(b)
            norms.append(n)
        elif len(n) > len(norms[dup_at]):
            kept[dup_at] = b
            norms[dup_at] = n
    return kept


def reconcile(blocks: list[Block]) -> list[Block]:
    """Drop text blocks contained in a non-text region, then dedup overlapping text.

    Guard against silent loss: only drop a covered text block when it's plausibly the region's
    own small label/caption (short AND a minor part of the region). A LONG text block that a
    mis-sized figure/table region happens to cover is real prose — keep it and flag it for review
    rather than silently dropping it into an untranslated crop (audit finding)."""
    nontext = [b for b in blocks if b.type in _NONTEXT and b.bbox]
    survivors: list[Block] = []
    for b in blocks:
        if b.type in _TEXT and b.bbox:
            cover = next((nt for nt in nontext if _contained(b.bbox, nt.bbox)), None)
            if cover is not None:
                small = (len(_norm(b.text)) <= 200
                         and _area(b.bbox) <= 0.5 * max(_area(cover.bbox), 1e-6))
                if small:
                    continue   # region's own label/caption — its crop/grid carries it
                b.flags["region_overlap"] = (
                    "text sits inside a figure/table region — kept (verify it isn't duplicated "
                    "by the crop)")
        survivors.append(b)
    return _dedup_text(survivors)
