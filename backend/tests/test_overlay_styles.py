"""Overlay carries block-level char styles it used to drop: strikethrough, small-caps, highlight,
all-caps — and still renders inline runs."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence, Document, Style

pytest.importorskip("fitz")


def _doc(style):
    d = Document(source_path="src.pdf", mime="application/pdf")
    d.page_sizes[0] = (400, 200)
    d.blocks = [Block(id="a", type=BlockType.PARAGRAPH, page=0,
                      text="hello", translated="halo dunia ini panjang sekali ya",
                      bbox=BBox(x0=20, y0=20, x1=380, y1=50), style=style, confidence=Confidence())]
    return d


def _overlay_html(monkeypatch, style):
    # capture the html passed to insert_htmlbox without needing a real source pdf
    import fitz

    from transdoc.regenerate import pdf_out
    captured = {}

    class _Page:
        rect = fitz.Rect(0, 0, 400, 200)
        page_count = 1

        def add_redact_annot(self, r): pass
        def apply_redactions(self, **k): pass
        def insert_htmlbox(self, r, html, **k):
            captured["html"] = html
            return (0, 1.0)

    class _PDF:
        page_count = 1
        def __getitem__(self, i): return _Page()
        def __iter__(self): return iter([_Page()])
        def save(self, *a, **k): pass
        def close(self): pass
        def pdf_catalog(self): return 0
        def xref_set_key(self, *a): pass
        def set_metadata(self, *a): pass
        def get_toc(self): return []

    monkeypatch.setattr(fitz, "open", lambda *a, **k: _PDF())
    pdf_out.render_overlay(_doc(style), Config(target_lang="id"), "/tmp/_x.pdf")
    return captured.get("html", "")


def test_overlay_strike_and_smallcaps(monkeypatch):
    html = _overlay_html(monkeypatch, Style(strike=True, small_caps=True))
    assert "line-through" in html and "small-caps" in html


def test_overlay_highlight(monkeypatch):
    html = _overlay_html(monkeypatch, Style(highlight="yellow"))
    assert "background-color" in html
