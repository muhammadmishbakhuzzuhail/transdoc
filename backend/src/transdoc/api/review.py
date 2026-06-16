"""Per-job review payload for the side-by-side feedback UI (PR-5).

A CAT-grade review screen needs every translated segment with its source, the produced
translation, and any QA / fuzzy / glossary signal — so the user can scan, spot the weak ones, and
correct them inline. ``build_review`` flattens the translated IR into exactly that, plus the run's
glossary + fuzzy suggestions. The job worker writes it to ``review.json`` and the API serves it.
"""

from __future__ import annotations

from ..ir import Document


def build_review(doc: Document) -> dict:
    """Flatten the translated document into a review payload: ordered segments + run suggestions.

    Segments carry their source bbox (PDF points) + the page size, so the review UI can map a
    clicked segment onto the rasterised page preview (PNG at a known dpi) — divide the page-point
    size by the PNG's natural pixel width to get the scale."""
    segments = []
    for b in doc.ordered_blocks():
        if not (b.is_translatable and b.translated):
            continue
        bbox = ([b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1] if b.bbox else None)
        segments.append({
            "block_id": b.id,
            "page": b.page,
            "bbox": bbox,
            "source": b.text,
            "translation": b.translated,
            "flags": sorted(b.flags.keys()),
        })
    return {
        "src_lang": doc.source_lang or "",
        "tgt_lang": doc.target_lang or "",
        "page_sizes": {str(p): [w, h] for p, (w, h) in (doc.page_sizes or {}).items()},
        "segments": segments,
        "glossary_suggestions": [
            {"term": t, "rendering": r, "kind": k}
            for t, r, k in getattr(doc, "glossary_suggestions", [])
        ],
        "fuzzy_suggestions": [
            {"source": s, "match_source": ms, "match_translation": mt, "score": sc}
            for s, ms, mt, sc in getattr(doc, "fuzzy_suggestions", [])
        ],
    }
