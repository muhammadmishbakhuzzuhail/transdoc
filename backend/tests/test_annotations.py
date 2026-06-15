"""Text-markup annotations (highlight/underline/strikeout): captured from the source PDF and
repainted in reconstruct (overlay keeps them natively)."""

from __future__ import annotations

import pytest

from transdoc.config import Config

fitz = pytest.importorskip("fitz")


def _annotated_pdf(tmp_path):
    d = fitz.open()
    p = d.new_page(width=300, height=300)
    p.insert_text((20, 50), "highlighted words here", fontsize=12)
    p.add_highlight_annot(fitz.Rect(18, 40, 180, 54))
    f = tmp_path / "a.pdf"
    d.save(str(f))
    d.close()
    return str(f)


def test_capture_highlight(tmp_path):
    from transdoc.extract.annots import capture
    s = fitz.open(_annotated_pdf(tmp_path))
    got = capture(s[0])
    s.close()
    assert got and got[0]["kind"] == "highlight" and got[0]["quads"]


def test_extract_carries_annots(tmp_path):
    from transdoc.extract.pdf import extract
    doc = extract(_annotated_pdf(tmp_path), Config(target_lang="id"))
    assert 0 in doc.page_annots and doc.page_annots[0][0]["kind"] == "highlight"


def test_reconstruct_repaints_highlight(tmp_path):
    from transdoc.extract.pdf import extract
    from transdoc.regenerate.pdf_out import render_reconstruct
    doc = extract(_annotated_pdf(tmp_path), Config(target_lang="id"))
    for b in doc.blocks:
        b.translated = (b.text or "") + " x"
    out = tmp_path / "o.pdf"
    render_reconstruct(doc, Config(target_lang="id"), str(out))
    r = fitz.open(str(out))
    # a yellow-ish pixel should exist in the highlighted band
    pix = r[0].get_pixmap(clip=fitz.Rect(20, 41, 170, 53))
    found = any(pix.pixel(x, y)[2] < 200 and pix.pixel(x, y)[0] > 200
                for x in range(0, pix.width, 10) for y in range(0, pix.height, 4))
    r.close()
    assert found


def test_redraw_annots_no_crash():
    from transdoc.regenerate.pdf_out import _redraw_annots
    out = fitz.open()
    page = out.new_page(width=200, height=200)
    _redraw_annots(page, [
        {"kind": "underline", "color": "#ff0000", "quads": [(10, 10, 100, 20)]},
        {"kind": "strikeout", "color": "#0000ff", "quads": [(10, 30, 100, 40)]},
    ])
    out.close()
