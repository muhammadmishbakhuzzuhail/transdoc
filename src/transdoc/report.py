"""Phase 6 — Translation Report (Markdown)."""

from __future__ import annotations

from .config import Config
from .ir import Document


def build_report(doc: Document, cfg: Config) -> str:
    p = doc.profile
    L: list[str] = ["# Translation Report", ""]

    L.append("## Document profile")
    L.append(f"- **Input nature:** {p.input_nature}")
    L.append(f"- **Damage level:** {p.damage_level}")
    if p.damage_examples:
        for ex in p.damage_examples:
            L.append(f"  - example: `{ex}`")
    L.append(f"- **Source language(s):** {', '.join(p.source_langs) or 'unknown'}")
    L.append(f"- **Target language:** {doc.target_lang or cfg.target_lang}")
    L.append(f"- **Genre:** {p.genre}")
    L.append(f"- **Reading order:** {p.reading_order_kind}")
    L.append(f"- **Structure:** {', '.join(p.structure) or 'n/a'}")
    L.append(f"- **Engine:** {cfg.engine.value} · **Fidelity:** "
             f"{cfg.resolve_fidelity(bool(doc.source_path and doc.source_path.endswith('.pdf'))).value}")
    L.append("")

    if doc.glossary:
        L.append("## Glossary")
        for g in doc.glossary:
            extra = f" — {g.rationale}" if g.rationale else ""
            L.append(f"- `{g.term}` → **{g.rendering}** ({g.action}){extra}")
        L.append("")

    if doc.repairs:
        L.append("## Reconstruction notes")
        for r in doc.repairs[:50]:
            L.append(f"- [{r.block_id}] {r.reason}: `{r.before[:40]}` → `{r.after[:40]}`")
        L.append("")

    # Rendering quality: how many overlaid blocks came out too small / shrunk to fit.
    illegible = [b for b in doc.blocks if "illegible" in b.flags]
    shrunk = [b for b in doc.blocks if "text_expansion" in b.flags]
    if illegible or shrunk:
        L.append("## Rendering quality (layout overlay)")
        if illegible:
            L.append(f"- ⚠️ **{len(illegible)} block(s) rendered below readable size** "
                     f"(< 6 pt) — the translation didn't fit the original box. This page is "
                     f"dense (e.g. a form); consider `--fidelity flow` or `--to docx` for a "
                     f"readable reflow.")
        if shrunk:
            L.append(f"- {len(shrunk)} block(s) shrunk to fit (still legible).")
        L.append("")

    flagged = doc.flagged_blocks()
    if flagged:
        L.append("## Flagged items (needs human check)")
        for b in flagged:
            loc = f"page {b.page+1}"
            flags = "; ".join(f"{k}: {v}" for k, v in b.flags.items())
            L.append(f"- **{loc}** [{b.type.value}] — {flags}")
            L.append(f"  - text: `{b.text[:80]}`")
        L.append("")

    L.append("## Risk flags")
    for rf in (p.risk_flags or ["none"]):
        L.append(f"- {rf}")
    L.append("")

    L.append("## Recommended human review")
    if flagged:
        L.append(f"- Review the {len(flagged)} flagged span(s) above, especially numbers/IDs/names.")
    if p.input_nature in ("scanned image", "photo/scan", "mixed"):
        L.append("- OCR was used — spot-check tables and any rotated/low-res regions.")
    if not flagged and p.input_nature == "clean digital":
        L.append("- Clean digital source; light review of terminology only.")
    L.append("")
    return "\n".join(L)
