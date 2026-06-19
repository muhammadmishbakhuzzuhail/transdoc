# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Reference-free QE annotation (COMET-Kiwi). The model is heavy/gated, so these tests stub the
estimator and exercise the wiring: scores -> confidence, qe_threshold -> low-quality flag, and
graceful no-op when the model is unavailable."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document
from transdoc.translate import quality


def _b(bid, text, translated):
    b = Block(id=bid, type=BlockType.PARAGRAPH, text=text)
    b.translated = translated
    return b


def _doc():
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Good source", "Terjemahan bagus"),
                _b("b", "Weak source", "Terjemahan lemah")]
    return d


def _cfg(**kw):
    return Config(source_lang="en", target_lang="id", quality_check=True, **kw)


def test_scores_written_and_threshold_flags(monkeypatch):
    # high score for a, low for b; default qe_threshold 0.75 -> only b flagged
    monkeypatch.setattr(quality.QualityEstimator, "score",
                        lambda self, pairs: [0.91, 0.40])
    d = _doc()
    quality.annotate_quality(d, _cfg())
    assert d.blocks[0].confidence.translation == 0.91
    assert d.blocks[1].confidence.translation == 0.40
    assert "low_translation_quality" not in d.blocks[0].flags
    assert "low_translation_quality" in d.blocks[1].flags


def test_uses_qe_threshold_not_flag_threshold(monkeypatch):
    # 0.85 is below the OCR flag_threshold (0.90) but above qe_threshold (0.75): must NOT flag,
    # proving QE reads the dedicated threshold and won't over-escalate.
    monkeypatch.setattr(quality.QualityEstimator, "score", lambda self, pairs: [0.85, 0.85])
    d = _doc()
    quality.annotate_quality(d, _cfg(flag_threshold=0.90, qe_threshold=0.75))
    assert not any("low_translation_quality" in b.flags for b in d.blocks)


def test_noop_when_model_unavailable(monkeypatch):
    monkeypatch.setattr(quality.QualityEstimator, "score",
                        lambda self, pairs: [None] * len(pairs))
    d = _doc()
    quality.annotate_quality(d, _cfg())
    assert all("low_translation_quality" not in b.flags for b in d.blocks)


def test_disabled_by_default(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(quality.QualityEstimator, "score",
                        lambda self, pairs: called.__setitem__("n", called["n"] + 1) or [0.1, 0.1])
    d = _doc()
    quality.annotate_quality(d, Config(source_lang="en", target_lang="id"))  # quality_check off
    assert called["n"] == 0
