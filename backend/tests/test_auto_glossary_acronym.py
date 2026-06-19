"""Auto-glossary must keep ALL-CAPS acronyms literal, not let the engine mistranslate them into
false-friend common words (TIN->TIMAH=tin metal, ZIP->RITSLETING=zipper) on a tax form."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document
from transdoc.translate.base import translate_document


class _FalseFriendEngine:
    """Mistranslates the tax acronyms (as a general MT does); echoes everything else."""
    cacheable = True
    _MAP = {"TIN": "TIMAH", "ZIP": "RITSLETING"}

    def translate_batch(self, texts, cfg, src=None):
        return [self._MAP.get(t.strip(), t) for t in texts]


def _doc():
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [
        Block(id="1", type=BlockType.PARAGRAPH, text="Enter your TIN on this line"),
        Block(id="2", type=BlockType.PARAGRAPH, text="Your TIN and ZIP are required"),
        Block(id="3", type=BlockType.PARAGRAPH, text="The ZIP must match the TIN"),
    ]
    return d


def test_acronyms_stay_literal_not_false_friends(monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    d = _doc()
    translate_document(d, _FalseFriendEngine(), Config(source_lang="en", target_lang="id"))
    out = " ".join(b.translated or "" for b in d.blocks)
    assert "TIMAH" not in out and "RITSLETING" not in out      # false friends suppressed
    assert "TIN" in out and "ZIP" in out                        # acronyms kept literal


def test_acronyms_not_in_glossary_suggestions(monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    d = _doc()
    translate_document(d, _FalseFriendEngine(), Config(source_lang="en", target_lang="id"))
    sug_terms = {t for t, _r, _k in getattr(d, "glossary_suggestions", [])}
    assert "TIN" not in sug_terms and "ZIP" not in sug_terms
