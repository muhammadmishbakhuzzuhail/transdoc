"""Page rotation (/Rotate) round-trip.

PyMuPDF reports a rotated page's rect + text coordinates in the *visual* (rotated) space, so:
- reconstruct rebuilds an upright page at the visual dimensions — rotation is baked in, the
  content lands right-side-up and in place (the output /Rotate is 0 but the view is identical);
- overlay edits the original page in place, so its native /Rotate is preserved exactly.
"""

from __future__ import annotations

import pytest

from transdoc.config import Config


def _rotated_pdf(tmp_path, deg=90):
    fitz = pytest.importorskip("fitz")
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((80, 120), "Rotated heading sample", fontsize=18)
    p.set_rotation(deg)
    f = tmp_path / "rot.pdf"
    d.save(str(f))
    d.close()
    return str(f)


def test_extract_visual_coords(tmp_path):
    from transdoc.extract.pdf import extract
    doc = extract(_rotated_pdf(tmp_path), Config(target_lang="id"))
    assert doc.page_rotation.get(0) == 90               # rotation captured + surfaced
    w, h = doc.page_sizes[0]
    assert (w, h) == (842.0, 595.0)                     # visual (rotated) dims
    for b in doc.blocks:                                # every bbox sits inside the visual page
        if b.bbox:
            assert 0 <= b.bbox.x0 and b.bbox.x1 <= w + 1
            assert 0 <= b.bbox.y0 and b.bbox.y1 <= h + 1


def test_reconstruct_upright_with_content(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.pdf import extract
    from transdoc.regenerate.pdf_out import render_reconstruct
    doc = extract(_rotated_pdf(tmp_path), Config(target_lang="id"))
    for b in doc.blocks:
        b.translated = (b.text or "") + " x"
    out = tmp_path / "recon.pdf"
    render_reconstruct(doc, Config(target_lang="id"), str(out))
    r = fitz.open(str(out))
    pg = r[0]
    assert (round(pg.rect.width), round(pg.rect.height)) == (842, 595)
    assert pg.rotation == 0                             # upright, rotation baked in
    assert "Rotated" in pg.get_text()                  # content placed, not lost
    r.close()


def test_overlay_keeps_native_rotation(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.pdf import extract
    from transdoc.regenerate.pdf_out import render_overlay
    doc = extract(_rotated_pdf(tmp_path), Config(target_lang="id"))
    for b in doc.blocks:
        b.translated = (b.text or "") + " x"
    out = tmp_path / "ovl.pdf"
    render_overlay(doc, Config(target_lang="id"), str(out))
    r = fitz.open(str(out))
    assert r[0].rotation == 90                          # native /Rotate preserved exactly
    r.close()
