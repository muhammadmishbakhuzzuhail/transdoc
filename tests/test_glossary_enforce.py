"""Glossary enforcement through translate_document: a supplied source->target term overrides
the engine output and is applied consistently (keys are protected verbatim, then mapped)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document
from transdoc.translate.echo import EchoTranslator


def test_glossary_terms_enforced():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="b", type=BlockType.PARAGRAPH, page=0,
                        text="The Transformer uses attention.",
                        confidence=Confidence(source="digital"))]
    cfg = Config(target_lang="id", glossary={"Transformer": "Transformator",
                                             "attention": "atensi"})
    translate_document(doc, EchoTranslator(), cfg)
    out = doc.blocks[0].translated
    assert "Transformator" in out and "atensi" in out
    assert "Transformer" not in out
