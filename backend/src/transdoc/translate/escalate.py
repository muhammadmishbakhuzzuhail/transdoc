"""Hybrid QE-gate (Area A3): re-translate only the QA-weak segments with the local doc-context LLM.

Validation showed full-document LLM translation is impractical on a small GPU (slow) and risky
(some models drift off-target), while the NMT is fast and clean. So the NMT translates the whole
document and the LLM is spent only where it pays: segments the QA suite flags HARD
(entity/untranslated/empty) or as a length anomaly, plus any the COMET model scored low. Each weak
segment is re-translated in its neighbour context (previous already-translated + following source),
so coherence holds without re-translating the rest.

Opt-in (cfg.escalate; needs Ollama). Best-effort: a failed LLM call keeps the NMT output — an
already-acceptable translation should never be lost to an escalation hiccup.
"""

from __future__ import annotations

from ..config import Config
from .base import _apply_glossary
from .protect import Protector


def _weak_ids(doc, findings) -> set[str]:
    """Block ids to escalate: any HARD QA finding or a length anomaly, plus COMET-flagged blocks."""
    ids = {f.block_id for f in findings if f.severity == "hard" or f.check == "length"}
    for b in doc.blocks:
        if "low_translation_quality" in getattr(b, "flags", {}):
            ids.add(b.id)
    return ids


def escalate_weak(doc, cfg: Config, findings) -> int:
    """Re-translate the weak blocks via the Ollama doc-context LLM, in place. Returns the count
    re-translated. Best-effort: keeps the existing (NMT) translation on any LLM failure."""
    weak = _weak_ids(doc, findings)
    if not weak:
        return 0
    blocks = [b for b in doc.blocks if b.is_translatable and b.translated]
    if not blocks:
        return 0

    from .ollama import OllamaError, OllamaTranslator
    tr = OllamaTranslator()
    glossary = dict(cfg.glossary)
    w = max(0, cfg.llm_context_window)
    n = 0
    for i, b in enumerate(blocks):
        if b.id not in weak:
            continue
        prev_pairs = [(blocks[j].text, blocks[j].translated)
                      for j in range(max(0, i - w), i) if blocks[j].translated]
        following = [blocks[j].text for j in range(i + 1, min(len(blocks), i + 1 + w))]
        protector = Protector(extra=list(glossary.keys()))
        protected, mapping = protector.protect(b.text)
        try:
            out = tr.translate_one(protected, cfg, src=doc.source_lang,
                                   prev_pairs=prev_pairs, following=following)
        except OllamaError:
            continue                                    # best-effort: keep the NMT translation
        out = protector.restore(out, mapping)
        b.translated = _apply_glossary(out, glossary)
        b.flags["llm_escalated"] = cfg.ollama_model
        n += 1
    tr.unload(cfg)            # free the LLM from (V)RAM once escalation is done
    return n
