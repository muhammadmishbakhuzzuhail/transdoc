"""Coloured page background: captured from the source PDF and repainted in reconstruct."""

from __future__ import annotations

import pytest

from transdoc.config import Config

fitz = pytest.importorskip("fitz")


def _bg_pdf(tmp_path, rgb=(0.85, 0.92, 1.0)):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.draw_rect(p.rect, color=rgb, fill=rgb)        # full-page coloured panel
    p.insert_text((80, 120), "text on a coloured page", fontsize=14)
    f = tmp_path / "bg.pdf"
    d.save(str(f))
    d.close()
    return str(f)


def test_capture_page_background(tmp_path):
    from transdoc.extract.pdf import extract
    doc = extract(_bg_pdf(tmp_path), Config(target_lang="id"))
    assert 0 in doc.page_background
    assert doc.page_background[0].lower() not in ("#ffffff", "#fff")


def test_white_page_no_background(tmp_path):
    from transdoc.extract.pdf import extract
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((80, 120), "plain white page", fontsize=14)
    f = tmp_path / "white.pdf"
    d.save(str(f))
    d.close()
    doc = extract(str(f), Config(target_lang="id"))
    assert doc.page_background == {}


def test_reconstruct_paints_background(tmp_path):
    from transdoc.extract.pdf import extract
    from transdoc.regenerate.pdf_out import render_reconstruct
    doc = extract(_bg_pdf(tmp_path), Config(target_lang="id"))
    for b in doc.blocks:
        b.translated = (b.text or "") + " x"
    out = tmp_path / "out.pdf"
    render_reconstruct(doc, Config(target_lang="id"), str(out))
    r = fitz.open(str(out))
    # sample a corner pixel — should be the coloured background, not white
    pix = r[0].get_pixmap(clip=fitz.Rect(5, 5, 15, 15))
    px = pix.pixel(0, 0)
    assert px != (255, 255, 255)
    r.close()
