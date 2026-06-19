# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Post-render verification (opt-in via cfg.verify).

The methodology the project leans on: don't trust the render — re-read it and compare. This
re-extracts the rendered output (PDF/DOCX) and diffs its structure against the source IR
(block / table / figure counts + total text length), returning human-readable warnings when the
output looks like it lost content. It does NOT re-translate; extraction only. Best-effort: any
failure becomes a single soft warning, never raises.
"""

from __future__ import annotations

from pathlib import Path

from .config import Config
from .ir import BlockType, Document


def _counts(doc: Document) -> tuple[int, int, int, int]:
    tables = sum(1 for b in doc.blocks if b.type == BlockType.TABLE)
    figures = sum(1 for b in doc.blocks if b.type == BlockType.FIGURE)
    textlen = sum(len(b.output_text or "") for b in doc.blocks)
    return len(doc.blocks), tables, figures, textlen


def verify_output(src_doc: Document, out_path: str, cfg: Config) -> list[str]:
    """Re-extract `out_path` and compare to `src_doc`. Returns a list of warning strings (empty
    when the output looks structurally faithful or can't be re-read)."""
    ext = Path(out_path).suffix.lower()
    if ext not in (".pdf", ".docx"):
        return []                                  # only re-extractable targets
    try:
        import copy

        from .extract import extract
        from .ingest.detect import detect
        vcfg = copy.copy(cfg)
        vcfg.layout = "off"                        # heuristic re-read: fast + no model needed
        out_doc = extract(detect(out_path), vcfg)
    except Exception as e:
        return [f"verify: could not re-read the output to check it ({type(e).__name__})"]

    sb, st, sf, stx = _counts(src_doc)
    ob, ot, of, otx = _counts(out_doc)
    warns: list[str] = []
    # Translated text length differs legitimately (±~40%); a large drop means lost content.
    if stx > 200 and otx < 0.5 * stx:
        warns.append(
            f"verify: output text is ~{otx / stx:.0%} of the source length — possible content loss")
    if ot < st:
        warns.append(f"verify: {st - ot} table(s) appear missing in the output")
    if of < sf:
        warns.append(f"verify: {sf - of} figure(s) appear missing in the output")
    return warns
