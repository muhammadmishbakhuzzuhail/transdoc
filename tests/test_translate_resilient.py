"""Per-segment resilience: if the batch translate fails (one segment every engine rejects),
the document still completes — good segments translate, the failed one keeps its source and
is flagged 'untranslated', instead of the whole document erroring out."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.base import translate_document


class _FlakyBatch:
    """Fails on any multi-item batch (simulates one bad segment sinking the batch); per-item
    works except for the segment containing 'BAD'."""

    name = "flaky"
    cacheable = False        # don't touch the persistent TM in the test

    def translate_batch(self, texts, cfg, src=None):
        if len(texts) > 1:
            raise RuntimeError("all fallback engines failed on some segment")
        t = texts[0]
        if "BAD" in t:
            raise RuntimeError("every engine rejected this segment")
        return [f"<{t}>"]


def test_one_bad_segment_does_not_sink_the_document():
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [
        Block(id="a", type=BlockType.PARAGRAPH, page=0, text="good one here",
              confidence=Confidence(source="digital")),
        Block(id="b", type=BlockType.PARAGRAPH, page=0, text="this is the BAD segment text",
              confidence=Confidence(source="digital")),
        Block(id="c", type=BlockType.PARAGRAPH, page=0, text="another good paragraph here",
              confidence=Confidence(source="digital")),
    ]
    translate_document(doc, _FlakyBatch(), Config(target_lang="id"))

    a, b, c = doc.blocks
    assert a.translated == "<good one here>"           # good segments translated
    assert c.translated == "<another good paragraph here>"
    assert b.translated == b.text                       # bad segment kept as source
    assert "untranslated" in b.flags                    # ...and flagged, not lost
