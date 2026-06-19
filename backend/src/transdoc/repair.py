# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""LLM OCR repair pass (Gap C) — `cfg.repair`, opt-in, runs BEFORE translation.

The extractor routes CID-garbage / scanned pages to OCR, and textnorm fixes hyphenation/ligatures,
but residual OCR mistakes (l/1, rn/m, merged or split words, stray punctuation) survive in
low-confidence blocks. This pass asks the local LLM (Ollama) to conservatively correct ONLY those
low-confidence OCR blocks, in the source language, before they are translated.

Safety first — the LLM can hallucinate, so:
  - only blocks flagged `low_ocr_confidence` (real OCR output the engine itself doubted) are touched;
  - the prompt forbids translating/paraphrasing/adding content (see OllamaTranslator.correct_ocr);
  - a correction that balloons the text (likely a hallucinated rewrite) is rejected;
  - every accepted edit is logged to doc.repairs (before/after/reason) so the report shows exactly
    what changed, and the original text is kept on any failure or uncertain block.
"""

from __future__ import annotations

from .ir import Repair

_MIN_LEN = 8          # tiny fragments aren't worth an LLM round-trip
_MAX_GROWTH = 1.5     # reject a "correction" much longer than the source -> hallucinated rewrite


def repair_ocr(doc, cfg) -> int:
    """Conservatively LLM-correct low-confidence OCR blocks in place. Returns the count repaired.
    No-op unless cfg.repair is set. Logs each edit to doc.repairs."""
    if not getattr(cfg, "repair", False):
        return 0
    targets = [b for b in doc.blocks
               if "low_ocr_confidence" in getattr(b, "flags", {})
               and b.text and len(b.text.strip()) >= _MIN_LEN]
    if not targets:
        return 0

    from .translate.ollama import OllamaError, OllamaTranslator
    tr = OllamaTranslator()
    n = 0
    for b in targets:
        before = b.text
        try:
            after = tr.correct_ocr(before, cfg, src=doc.source_lang)
        except OllamaError:
            continue                                  # best-effort: keep the original OCR text
        after = (after or "").strip()
        if not after or after == before.strip():
            continue                                  # declined / no change
        if len(after) > _MAX_GROWTH * len(before) + 10:
            continue                                  # ballooned -> likely hallucination, reject
        b.text = after
        b.flags["ocr_repaired"] = "llm"
        doc.repairs.append(Repair(block_id=b.id, before=before, after=after, reason="ocr-llm"))
        n += 1
    tr.unload(cfg)            # free the LLM from (V)RAM before later GPU work (COMET QE)
    return n
