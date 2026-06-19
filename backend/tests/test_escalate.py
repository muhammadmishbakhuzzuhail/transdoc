# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Hybrid QE-gate: only QA-weak segments are re-translated by the LLM; clean ones untouched;
a failed LLM call keeps the NMT output (best-effort)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.escalate import escalate_weak
from transdoc.translate.ollama import OllamaError, OllamaTranslator
from transdoc.translate.qa import run_qa


def _doc():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.source_lang = "en"
    weak = Block(id="w", type=BlockType.PARAGRAPH, page=0, text="Pay 1500 dollars now",
                 confidence=Confidence(source="digital"))
    weak.translated = "Bayar dolar sekarang"            # 1500 dropped -> entity HARD -> weak
    clean = Block(id="c", type=BlockType.PARAGRAPH, page=0, text="The weather is nice today",
                  confidence=Confidence(source="digital"))
    clean.translated = "Cuaca hari ini bagus"
    doc.blocks = [weak, clean]
    return doc


def test_escalates_only_weak_block(monkeypatch):
    monkeypatch.setattr(OllamaTranslator, "translate_one",
                        lambda self, text, cfg, src=None, prev_pairs=None, following=None:
                        "LLM:" + text)
    doc = _doc()
    findings = run_qa(doc, Config(target_lang="id"))
    n = escalate_weak(doc, Config(target_lang="id"), findings)
    assert n == 1
    assert doc.blocks[0].translated.startswith("LLM:") and "1500" in doc.blocks[0].translated
    assert "llm_escalated" in doc.blocks[0].flags
    assert doc.blocks[1].translated == "Cuaca hari ini bagus"      # clean block untouched


def test_best_effort_keeps_nmt_on_llm_failure(monkeypatch):
    def _boom(self, text, cfg, src=None, prev_pairs=None, following=None):
        raise OllamaError("ollama down")

    monkeypatch.setattr(OllamaTranslator, "translate_one", _boom)
    doc = _doc()
    findings = run_qa(doc, Config(target_lang="id"))
    n = escalate_weak(doc, Config(target_lang="id"), findings)
    assert n == 0
    assert doc.blocks[0].translated == "Bayar dolar sekarang"      # NMT output preserved


def test_no_weak_segments_is_noop(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(OllamaTranslator, "translate_one",
                        lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "x")
    doc = Document(source_path="x.txt", mime="text/plain")
    b = Block(id="c", type=BlockType.PARAGRAPH, page=0, text="The weather is nice today",
              confidence=Confidence(source="digital"))
    b.translated = "Cuaca hari ini bagus"
    doc.blocks = [b]
    findings = run_qa(doc, Config(target_lang="id"))
    assert escalate_weak(doc, Config(target_lang="id"), findings) == 0
    assert called["n"] == 0                                        # LLM never called


def test_comet_flagged_block_is_escalated(monkeypatch):
    monkeypatch.setattr(OllamaTranslator, "translate_one",
                        lambda self, text, cfg, src=None, prev_pairs=None, following=None:
                        "LLM:" + text)
    doc = Document(source_path="x.txt", mime="text/plain")
    b = Block(id="q", type=BlockType.PARAGRAPH, page=0, text="A perfectly clean sentence here",
              confidence=Confidence(source="digital"))
    b.translated = "Kalimat yang bersih sempurna di sini"
    b.flags["low_translation_quality"] = "QE 40%"                  # COMET-flagged, no rule finding
    doc.blocks = [b]
    findings = run_qa(doc, Config(target_lang="id"))               # no rule findings
    assert escalate_weak(doc, Config(target_lang="id"), findings) == 1
    assert doc.blocks[0].translated.startswith("LLM:")
