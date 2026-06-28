# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""QE-gated engine selection — the biggest offline translation-quality lever.

No single MT engine dominates across language pairs: Opus-MT wins European pairs, IndicTrans2 wins
Indic, NLLB has the broadest coverage, the online endpoint is a strong all-rounder. So instead of
fixing one engine, translate a SAMPLE of the document with each candidate, score every candidate
reference-free with COMET-Kiwi, and run the whole document through the winner (doc-MT "QE-pick-best",
technique #2 in the literature — the largest accuracy gain achievable on CPU without an LLM).

Resource discipline (6 GB GPU): candidate engines load one at a time and are released before the
next, and QE is loaded once at the end, so peak GPU stays at a single model. The scoring/selection
is a pure function with injectable translate/score deps so it's testable offline (no models).
"""

from __future__ import annotations

import logging

from ..config import Config, Engine

log = logging.getLogger(__name__)


def _free_cuda() -> None:
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def select_engine(doc, cfg: Config, candidates, *, sample_size: int = 12, min_chars: int = 20,
                  translate_fn=None, score_fn=None):
    """Pick the best engine for this document by reference-free QE on a sample.

    Returns ``(winner: Engine, result: dict)`` where result is
    ``{"winner": str, "scores": {engine_value: mean_qe}, "sample": n}`` (empty scores when selection
    couldn't run — too little text, or QE unavailable — in which case the winner is ``cfg.engine``).

    ``translate_fn(engine, texts) -> list[str]`` and ``score_fn(pairs) -> list[float|None]`` are
    injected in tests; the defaults build a real translator per engine (released after use) and the
    COMET-Kiwi estimator (kept loaded so the pipeline's QE phase reuses it)."""
    # primary engine is always a candidate; dedupe, drop the no-op echo
    cands: list[Engine] = []
    for e in [cfg.engine, *candidates]:
        if e != Engine.ECHO and e not in cands:
            cands.append(e)
    if len(cands) < 2:
        return cfg.engine, {"winner": cfg.engine.value, "scores": {}, "sample": 0}

    sample = sorted((b for b in doc.translatable_blocks() if len(b.text.strip()) >= min_chars),
                    key=lambda b: len(b.text), reverse=True)[:sample_size]
    if len(sample) < 2:                       # not enough text to choose on — keep the primary
        return cfg.engine, {"winner": cfg.engine.value, "scores": {}, "sample": len(sample)}
    srcs = [b.text for b in sample]

    src_lang = (doc.source_lang or cfg.source_lang or "auto")
    translate_fn = translate_fn or _make_translate_fn(cfg, src_lang)
    score_fn = score_fn or _default_score

    # translate the sample with each candidate, releasing each engine before the next
    outs: dict[Engine, list[str]] = {}
    for eng in cands:
        try:
            mts = translate_fn(eng, srcs)
        except Exception as e:
            log.warning("engine selection: %s failed (%s: %s)", eng.value, type(e).__name__, e)
            continue
        if mts and len(mts) == len(srcs):
            outs[eng] = mts

    # score every candidate once (QE loaded a single time)
    scores: dict[str, float] = {}
    for eng, mts in outs.items():
        pairs = [(s, m) for s, m in zip(srcs, mts) if m.strip()]
        if not pairs:
            continue
        vals = [v for v in score_fn(pairs) if v is not None]
        if vals:
            scores[eng.value] = round(sum(vals) / len(vals), 4)

    if not scores:                            # QE unavailable / nothing scorable -> keep the primary
        return cfg.engine, {"winner": cfg.engine.value, "scores": {}, "sample": len(sample)}

    winner_value = max(scores, key=lambda k: scores[k])
    winner = Engine(winner_value)
    return winner, {"winner": winner_value, "scores": scores, "sample": len(sample)}


def _make_translate_fn(cfg: Config, src_lang: str):
    from ..translate import get_translator

    def _translate(engine: Engine, texts: list[str]) -> list[str]:
        c = cfg.model_copy(update={"engine": engine})
        tr = get_translator(c)
        try:
            return tr.translate_batch(texts, c, src=None if src_lang == "auto" else src_lang)
        finally:
            rel = getattr(tr, "release", None)
            if callable(rel):
                rel()
            _free_cuda()

    return _translate


def _default_score(pairs):
    # reuse the pipeline's QE estimator (cached) so the later quality_check phase doesn't reload it
    from .quality import QualityEstimator
    return QualityEstimator().score(pairs)
