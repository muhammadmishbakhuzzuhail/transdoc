"""Serialise the full analysis of a finished job to a plain dict (-> analysis.json) so the UI
can render all of it: document profile, flagged items, glossary, reconstruction notes,
rendering-quality warnings and layout-region counts."""

from __future__ import annotations

from ..config import Config
from ..ir import Document


def build_analysis(doc: Document, cfg: Config) -> dict:
    p = doc.profile
    flagged = doc.flagged_blocks()
    illegible = sum(1 for b in doc.blocks if "illegible" in b.flags)
    shrunk = sum(1 for b in doc.blocks if "shrunk" in b.flags)
    crops = sum(1 for b in doc.blocks if getattr(b, "crop_region", False))
    return {
        "profile": {
            "input_nature": p.input_nature,
            "damage_level": p.damage_level,
            "damage_examples": p.damage_examples,
            "source_langs": p.source_langs,
            "target_lang": doc.target_lang or cfg.target_lang,
            "genre": p.genre,
            "structure": p.structure,
            "reading_order": p.reading_order_kind,
            "risk_flags": p.risk_flags,
        },
        "counts": {
            "blocks": len(doc.blocks),
            "flagged": len(flagged),
            "pages": doc.page_count,
        },
        "rendering": {"illegible": illegible, "shrunk": shrunk},
        "layout": {"crops": crops, "enabled": cfg.layout != "off"},
        "flagged": [
            {
                "page": b.page + 1,
                "type": b.type.value,
                "flags": b.flags,
                "text": (b.text or "")[:160],
                "source": b.confidence.source if b.confidence else None,
                "lang": b.lang,
            }
            for b in flagged[:200]
        ],
        "glossary": [
            {"term": g.term, "rendering": g.rendering, "action": g.action,
             "rationale": g.rationale}
            for g in doc.glossary[:200]
        ],
        "repairs": [
            {"block_id": r.block_id, "before": r.before[:80], "after": r.after[:80],
             "reason": r.reason}
            for r in doc.repairs[:200]
        ],
    }
