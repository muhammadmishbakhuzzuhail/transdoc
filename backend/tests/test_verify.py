# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Post-render verification: re-extract output, diff structure, warn on content loss."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document


def _doc(blocks):
    d = Document(source_path="x", mime="application/pdf")
    d.blocks = blocks
    return d


def _p(text):
    return Block(id=text[:4], type=BlockType.PARAGRAPH, text=text,
                 bbox=BBox(x0=0, y0=0, x1=1, y1=1), confidence=Confidence())


def test_non_extractable_target_skipped(tmp_path):
    from transdoc.verify import verify_output
    out = tmp_path / "o.md"
    out.write_text("hi")
    assert verify_output(_doc([_p("x" * 300)]), str(out), Config(target_lang="id")) == []


def test_warns_on_missing_table(tmp_path, monkeypatch):
    from transdoc import verify as V
    from transdoc.ir import Table
    src = _doc([Block(id="t", type=BlockType.TABLE, table=Table(rows=[]),
                      bbox=BBox(x0=0, y0=0, x1=1, y1=1), confidence=Confidence()),
               _p("body text long enough to count here and there " * 6)])
    # fake re-extraction returning a doc with no table + much less text
    monkeypatch.setattr(V, "detect", lambda p: object(), raising=False)
    import transdoc.extract as EX
    monkeypatch.setattr("transdoc.ingest.detect.detect", lambda p: object())
    monkeypatch.setattr(EX, "extract", lambda det, cfg: _doc([_p("short")]))
    # point verify at the patched extract/detect via its imports
    monkeypatch.setattr("transdoc.verify.detect", lambda p: object(), raising=False)
    warns = V.verify_output(src, str(tmp_path / "o.pdf"), Config(target_lang="id"))
    assert any("table" in w for w in warns) or any("content loss" in w for w in warns)


def test_clean_roundtrip_no_warn(tmp_path, monkeypatch):
    from transdoc import verify as V
    src = _doc([_p("a paragraph of body text that is reasonably long here " * 4)])
    monkeypatch.setattr("transdoc.ingest.detect.detect", lambda p: object())
    import transdoc.extract as EX
    monkeypatch.setattr(EX, "extract",
                        lambda det, cfg: _doc([_p("setara terjemahan yang panjangnya mirip sekali " * 4)]))
    assert V.verify_output(src, str(tmp_path / "o.pdf"), Config(target_lang="id")) == []
