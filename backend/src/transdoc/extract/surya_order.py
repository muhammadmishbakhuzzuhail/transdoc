# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Surya reading-order re-ranking (PR-3, opt-in) — `cfg.reading_order_engine == "surya"`.

The default reading order is the deterministic XY-cut (extract/reading_order.py): fast, CPU-free,
and good on clean column layouts. It can mis-order genuinely hard pages (interleaved columns,
floating footnotes/sidebars). Surya ships a layout VLM that predicts a reading *position* per
region; this pass renders each PDF page, asks Surya for the ordered regions, matches our extracted
blocks to those regions by IoU, and re-numbers `reading_order` to follow Surya.

PDF only (it needs a page raster). Slow (a VLM on CPU) and the Surya model is non-commercial, so it
stays opt-in. Any failure (surya-ocr missing, model download blocked, empty prediction) leaves the
XY-cut order untouched — never worse than the default.
"""

from __future__ import annotations

from ..ir import Document

_UNMATCHED = 10 ** 6        # blocks Surya didn't cover sort after the matched ones, order preserved


class SuryaOrderer:
    _pred = None
    _ok = True

    def _load(self):
        if SuryaOrderer._pred is None and SuryaOrderer._ok:
            try:
                from surya.layout import LayoutPredictor

                SuryaOrderer._pred = LayoutPredictor()
            except Exception:
                SuryaOrderer._ok = False        # surya-ocr missing / model unavailable
        return SuryaOrderer._pred

    def order_page(self, image) -> list[tuple[float, float, float, float]]:
        """Return Surya's layout boxes in reading order, as (x0,y0,x1,y1) in IMAGE pixels.
        Empty list on any failure."""
        pred = self._load()
        if pred is None:
            return []
        try:
            res = pred([image])[0]
            boxes = sorted(res.bboxes, key=lambda b: b.position)
            return [tuple(b.bbox) for b in boxes]
        except Exception:
            return []


def _iou(a, b) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _reorder_page(blocks, boxes_pt) -> int:
    """Re-number `reading_order` of one page's blocks to follow `boxes_pt` (Surya boxes in points,
    already in reading order). Each block takes the position of its best-IoU Surya box; unmatched
    blocks keep their relative order and sort last. Stable. Returns 1 if anything moved, else 0."""
    if not blocks or not boxes_pt:
        return 0
    pos_of: dict[int, int] = {}
    for b in blocks:
        bb = (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1)
        best_pos, best_iou = _UNMATCHED, 0.0
        for pos, sb in enumerate(boxes_pt):
            iou = _iou(bb, sb)
            if iou > best_iou:
                best_iou, best_pos = iou, pos
        pos_of[id(b)] = best_pos
    ordered = sorted(blocks, key=lambda b: (pos_of[id(b)], b.reading_order))
    if all(ordered[k] is blocks[k] for k in range(len(blocks))):
        return 0                                # already in Surya order — nothing to do
    base = min(b.reading_order for b in blocks)
    for k, b in enumerate(ordered):
        b.reading_order = base + k
    return 1


def surya_reading_order(doc: Document, cfg) -> int:
    """Re-rank reading order via Surya for a PDF document. Returns the number of pages reordered.
    No-op (returns 0) unless cfg.reading_order_engine == 'surya', the source is a PDF, and Surya
    loads."""
    if getattr(cfg, "reading_order_engine", "xycut") != "surya":
        return 0
    if doc.mime != "application/pdf":
        return 0
    orderer = SuryaOrderer()
    if orderer._load() is None:
        return 0

    import fitz
    from PIL import Image

    from ..layout.structure import render_page_array

    by_page: dict[int, list] = {}
    for b in doc.blocks:
        if b.bbox:
            by_page.setdefault(b.page, []).append(b)
    if not by_page:
        return 0

    pages = 0
    with fitz.open(doc.source_path) as fdoc:
        for pno, blocks in by_page.items():
            if pno >= fdoc.page_count:
                continue
            arr, scale = render_page_array(fdoc[pno])      # region_pixels * scale -> points
            boxes_px = orderer.order_page(Image.fromarray(arr))
            if not boxes_px:
                continue
            boxes_pt = [tuple(c * scale for c in bx) for bx in boxes_px]
            pages += _reorder_page(blocks, boxes_pt)
    return pages
