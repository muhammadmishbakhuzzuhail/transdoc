"""Per-job review payload for the side-by-side feedback UI (PR-5).

A CAT-grade review screen needs every translated segment with its source, the produced
translation, and any QA / fuzzy / glossary signal — so the user can scan, spot the weak ones, and
correct them inline. ``build_review`` flattens the translated IR into exactly that, plus the run's
glossary + fuzzy suggestions. The job worker writes it to ``review.json`` and the API serves it.
"""

from __future__ import annotations

from ..ir import Document


def build_review(doc: Document) -> dict:
    """Flatten the translated document into a review payload: ordered segments + run suggestions."""
    segments = []
    for b in doc.blocks:
        if not (b.is_translatable and b.translated):
            continue
        segments.append({
            "block_id": b.id,
            "page": b.page,
            "source": b.text,
            "translation": b.translated,
            "flags": sorted(b.flags.keys()),
        })
    return {
        "src_lang": doc.source_lang or "",
        "tgt_lang": doc.target_lang or "",
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
