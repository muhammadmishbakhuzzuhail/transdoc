# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""QE-gated engine selection: the sample is translated by each candidate and the best mean
COMET-Kiwi score wins. Deps injected so it runs offline (no engines, no COMET)."""

from __future__ import annotations

from transdoc.config import Config, Engine
from transdoc.ir import BBox, Block, BlockType, Confidence, Document
from transdoc.translate.select import select_engine


def _doc(n=4):
    d = Document(source_path="x.pdf", mime="application/pdf", page_count=1, source_lang="en")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    d.blocks = [
        Block(id=str(i), type=BlockType.PARAGRAPH, reading_order=i, bbox=bb,
              text=f"A translatable sentence number {i} with enough words to score.",
              confidence=Confidence())
        for i in range(n)
    ]
    return d


def test_picks_highest_scoring_engine():
    doc = _doc()
    cfg = Config(target_lang="id", engine=Engine.GOOGLE)

    # opusmt scores best, nllb worst; google middling
    per_engine = {Engine.GOOGLE: 0.70, Engine.OPUSMT: 0.85, Engine.NLLB: 0.60}

    def translate_fn(engine, texts):
        return [f"[{engine.value}] {t}" for t in texts]

    def score_fn(pairs):
        # infer the engine from the marker translate_fn injected
        eng = pairs[0][1].split("]")[0].strip("[")
        return [per_engine[Engine(eng)]] * len(pairs)

    winner, result = select_engine(doc, cfg, [Engine.OPUSMT, Engine.NLLB],
                                   translate_fn=translate_fn, score_fn=score_fn)
    assert winner == Engine.OPUSMT
    assert result["winner"] == "opusmt"
    assert set(result["scores"]) == {"google", "opusmt", "nllb"}
    assert result["scores"]["opusmt"] > result["scores"]["google"]


def test_falls_back_to_primary_when_qe_unavailable():
    doc = _doc()
    cfg = Config(target_lang="id", engine=Engine.GOOGLE)
    winner, result = select_engine(
        doc, cfg, [Engine.OPUSMT],
        translate_fn=lambda e, t: list(t),
        score_fn=lambda pairs: [None] * len(pairs),     # COMET not installed
    )
    assert winner == Engine.GOOGLE
    assert result["scores"] == {}


def test_no_candidates_keeps_primary():
    doc = _doc()
    cfg = Config(target_lang="id", engine=Engine.GOOGLE)
    # only echo + primary -> nothing to choose
    winner, result = select_engine(doc, cfg, [Engine.ECHO],
                                   translate_fn=lambda e, t: list(t),
                                   score_fn=lambda p: [1.0] * len(p))
    assert winner == Engine.GOOGLE
    assert result["scores"] == {}


def test_too_little_text_keeps_primary():
    d = Document(source_path="x.pdf", mime="application/pdf", page_count=1, source_lang="en")
    bb = BBox(x0=0, y0=0, x1=1, y1=1)
    d.blocks = [Block(id="0", type=BlockType.PARAGRAPH, reading_order=0, bbox=bb, text="short",
                      confidence=Confidence())]
    cfg = Config(target_lang="id", engine=Engine.GOOGLE)
    winner, result = select_engine(d, cfg, [Engine.OPUSMT],
                                   translate_fn=lambda e, t: list(t),
                                   score_fn=lambda p: [1.0] * len(p))
    assert winner == Engine.GOOGLE
