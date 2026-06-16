"""Ollama doc-context translator: id-alignment, sliding-window carry, retry -> hard-fail.

No real HTTP — OllamaTranslator._call is stubbed to parse the request payload and return a canned
JSON response, so we test the windowing/alignment/parse/retry logic deterministically.
"""

from __future__ import annotations

import json

import pytest

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document
from transdoc.translate.ollama import OllamaError, OllamaTranslator


@pytest.fixture(autouse=True)
def _isolated_tm(tmp_path, monkeypatch):
    """Point the TM store at a throwaway DB (never the real user DB) + isolate the legacy import.
    Re-enable the TM here (conftest disables it session-wide) so the context-hash cache is exercised;
    safe because the DB is the per-test tmp file."""
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "transdoc.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "nolegacy.sqlite"))
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    yield
    TMStore._instance = None


def _fake_call_factory(record=None, drop_id=None):
    """Return a _call(self, cfg, system, user) that translates each item to 'T:'+text, optionally
    recording payloads and optionally dropping one id (to trigger an alignment failure)."""
    def _call(self, cfg, system, user):
        payload = json.loads(user)
        if record is not None:
            record.append(payload)
        out = {}
        for it in payload["items"]:
            if drop_id is not None and it["id"] == drop_id:
                continue
            out[it["id"]] = "T:" + it["text"]
        return json.dumps({"translations": out})
    return _call


def test_translate_segments_aligned(monkeypatch):
    monkeypatch.setattr(OllamaTranslator, "_call", _fake_call_factory())
    cfg = Config(target_lang="id")
    out = OllamaTranslator().translate_segments(["Alpha", "Beta", "Gamma"], cfg, src="en")
    assert out == ["T:Alpha", "T:Beta", "T:Gamma"]


def test_sliding_window_carries_previous_translations(monkeypatch):
    record: list = []
    monkeypatch.setattr(OllamaTranslator, "_call", _fake_call_factory(record=record))
    cfg = Config(target_lang="id", ollama_num_ctx=1, llm_context_window=2)  # tiny budget -> chunking
    texts = ["x" * 1500, "y" * 1500, "z" * 1500]                           # each forces its own chunk
    out = OllamaTranslator().translate_segments(texts, cfg, src="en")
    assert out == ["T:" + t for t in texts]
    # 3 chunks; chunk 2's context_before carries the TRANSLATED neighbours (not raw source)
    assert len(record) == 3
    ctx_before_3rd = record[2]["context_before"]
    assert ctx_before_3rd and ctx_before_3rd[-1]["translation"] == "T:" + texts[1]
    # following context is the next source segment(s), read-only
    assert record[0]["context_after"] and record[0]["context_after"][0] == texts[1]


def test_alignment_mismatch_single_segment_hard_fails(monkeypatch):
    # id "1" is ALWAYS dropped, even alone -> splitting can't recover -> hard-fail (no silent fallback)
    monkeypatch.setattr(OllamaTranslator, "_call", _fake_call_factory(drop_id="1"))
    monkeypatch.setattr("time.sleep", lambda *_: None)
    with pytest.raises(OllamaError):
        OllamaTranslator().translate_segments(["a", "b", "c"], Config(target_lang="id"))


def test_alignment_failure_recovers_by_splitting(monkeypatch):
    # the model drops an id only in MULTI-item batches; splitting down to singles recovers all.
    def _call(self, cfg, system, user):
        items = json.loads(user)["items"]
        out = {}
        for it in items:
            if it["id"] == "1" and len(items) > 1:      # flaky only in a batch
                continue
            out[it["id"]] = "T:" + it["text"]
        return json.dumps({"translations": out})

    monkeypatch.setattr(OllamaTranslator, "_call", _call)
    out = OllamaTranslator().translate_segments(["a", "b", "c"], Config(target_lang="id"))
    assert out == ["T:a", "T:b", "T:c"]                 # split recovered the dropped segment


def test_doc_context_path_through_translate_document(monkeypatch):
    monkeypatch.setattr(OllamaTranslator, "_call", _fake_call_factory())
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="b0", type=BlockType.PARAGRAPH, page=0, text="Hello world.",
                        confidence=Confidence(source="digital")),
                  Block(id="b1", type=BlockType.PARAGRAPH, page=0, text="Second line.",
                        confidence=Confidence(source="digital"))]
    translate_document(doc, OllamaTranslator(), Config(target_lang="id", auto_glossary=False))
    assert doc.blocks[0].translated == "T:Hello world."
    assert doc.blocks[1].translated == "T:Second line."


def test_protect_placeholder_preserved_under_llm(monkeypatch):
    # numbers/urls are protected to [PH..] before the engine; the stub keeps them, restore brings
    # them back verbatim — so the digits survive the LLM path.
    monkeypatch.setattr(OllamaTranslator, "_call", _fake_call_factory())
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="b0", type=BlockType.PARAGRAPH, page=0,
                        text="Pay 1500 at https://x.io now.",
                        confidence=Confidence(source="digital"))]
    translate_document(doc, OllamaTranslator(), Config(target_lang="id", auto_glossary=False))
    assert "1500" in doc.blocks[0].translated and "https://x.io" in doc.blocks[0].translated


def test_context_hash_cache_skips_engine_on_rerun(monkeypatch):
    calls = {"n": 0}
    base = _fake_call_factory()

    def counting(self, cfg, system, user):
        calls["n"] += 1
        return base(self, cfg, system, user)

    monkeypatch.setattr(OllamaTranslator, "_call", counting)

    def run():
        doc = Document(source_path="x.txt", mime="text/plain")
        doc.source_lang = "en"
        doc.blocks = [Block(id="b0", type=BlockType.PARAGRAPH, page=0, text="Alpha beta gamma.",
                            confidence=Confidence(source="digital")),
                      Block(id="b1", type=BlockType.PARAGRAPH, page=0, text="Delta epsilon zeta.",
                            confidence=Confidence(source="digital"))]
        translate_document(doc, OllamaTranslator(), Config(target_lang="id", auto_glossary=False))
        return doc

    d1 = run()
    n_after_first = calls["n"]
    assert n_after_first > 0
    d2 = run()                                    # identical doc -> full context-hash cache hit
    assert calls["n"] == n_after_first            # engine NOT called again
    assert d2.blocks[0].translated == d1.blocks[0].translated
    assert d2.blocks[1].translated == d1.blocks[1].translated
