# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""LLM OCR repair pass. The Ollama call is stubbed; these cover the gating, the low-confidence
targeting, the hallucination guard, and the doc.repairs logging."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document
from transdoc import repair as repair_mod
from transdoc.translate.ollama import OllamaTranslator


def _b(bid, text, low_conf=True):
    b = Block(id=bid, type=BlockType.PARAGRAPH, text=text)
    if low_conf:
        b.flags["low_ocr_confidence"] = "55%"
    return b


def _doc(*blocks):
    d = Document(source_path="x.pdf", mime="application/pdf")
    d.blocks = list(blocks)
    return d


def _cfg():
    return Config(source_lang="en", target_lang="id", repair=True)


def _stub(monkeypatch, fn):
    monkeypatch.setattr(OllamaTranslator, "correct_ocr",
                        lambda self, text, cfg, src=None: fn(text))
    monkeypatch.setattr(OllamaTranslator, "unload", lambda self, cfg: None)   # no network in tests


def test_repairs_low_conf_block_and_logs(monkeypatch):
    _stub(monkeypatch, lambda t: "The quick brown fox.")
    d = _doc(_b("a", "Tne qulck brown f0x."))
    assert repair_mod.repair_ocr(d, _cfg()) == 1
    assert d.blocks[0].text == "The quick brown fox."
    assert d.blocks[0].flags.get("ocr_repaired") == "llm"
    assert len(d.repairs) == 1
    assert d.repairs[0].block_id == "a" and d.repairs[0].reason == "ocr-llm"
    assert d.repairs[0].before == "Tne qulck brown f0x."


def test_skips_high_confidence_blocks(monkeypatch):
    _stub(monkeypatch, lambda t: "CHANGED")
    d = _doc(_b("a", "Clean digital text here.", low_conf=False))
    assert repair_mod.repair_ocr(d, _cfg()) == 0
    assert d.blocks[0].text == "Clean digital text here."
    assert not d.repairs


def test_rejects_ballooned_correction(monkeypatch):
    _stub(monkeypatch, lambda t: t + " " + "extra " * 40)   # hallucinated expansion
    d = _doc(_b("a", "Short ocr line."))
    assert repair_mod.repair_ocr(d, _cfg()) == 0
    assert d.blocks[0].text == "Short ocr line."


def test_unchanged_output_is_noop(monkeypatch):
    _stub(monkeypatch, lambda t: t)                         # model returns it unchanged
    d = _doc(_b("a", "Already fine text."))
    assert repair_mod.repair_ocr(d, _cfg()) == 0
    assert not d.repairs


def test_tiny_fragment_skipped(monkeypatch):
    _stub(monkeypatch, lambda t: "XYZ")
    d = _doc(_b("a", "ok"))                                 # below _MIN_LEN
    assert repair_mod.repair_ocr(d, _cfg()) == 0


def test_disabled_by_default(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(OllamaTranslator, "correct_ocr",
                        lambda self, text, cfg, src=None: called.__setitem__("n", called["n"] + 1) or text)
    d = _doc(_b("a", "Tne qulck brown f0x."))
    assert repair_mod.repair_ocr(d, Config(source_lang="en", target_lang="id")) == 0  # repair off
    assert called["n"] == 0
