# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""LAYOUT overlay fidelity: page background (logos/graphics) survives, and character
styling (bold/italic/colour/size) is captured from the source and carried to the overlay.
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _styled_pdf(path: str) -> None:
    """A page with a light-blue background box, a red 'logo' image, and red text on top."""
    doc = fitz.open()
    pg = doc.new_page(width=500, height=300)
    pg.draw_rect(fitz.Rect(0, 0, 500, 300), fill=(0.85, 0.92, 1.0))
    logo = fitz.open()
    lp = logo.new_page(width=60, height=60)
    lp.draw_rect(fitz.Rect(0, 0, 60, 60), fill=(1, 0, 0))
    pg.insert_image(fitz.Rect(20, 20, 80, 80), pixmap=lp.get_pixmap())
    # long enough (>20 chars) so the page is classified digital, not scanned
    pg.insert_text((100, 120), "The quick brown fox jumps over the lazy dog today.",
                   fontsize=14, color=(0.8, 0, 0))
    doc.save(path)


def test_extractor_captures_colour_and_size(tmp_path):
    src = tmp_path / "s.pdf"
    _styled_pdf(str(src))
    doc = extract(str(src), Config(target_lang="id"))
    text = [b for b in doc.blocks if b.is_translatable][0]
    assert text.style.size == pytest.approx(14.0, abs=0.5)
    assert text.style.color == "#cc0000"


def test_overlay_preserves_background_logo(tmp_path):
    src = tmp_path / "s.pdf"
    _styled_pdf(str(src))
    out = tmp_path / "s.id.pdf"
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.LAYOUT, mode=Mode.FULL)
    run(str(src), cfg, out_path=str(out))

    page = fitz.open(str(out))[0]
    # logo image + background drawing both survive the text redaction
    assert len(page.get_images()) == 1
    assert len(page.get_drawings()) >= 1
    pix = page.get_pixmap()
    assert pix.pixel(40, 40) == (255, 0, 0)            # logo still red
    r, g, b = pix.pixel(450, 280)                       # background still blue-ish, not white
    assert (r, g, b) != (255, 255, 255) and b > r
    # source glyphs were removed: the phrase appears exactly once (in the [id] translation),
    # not twice (which would mean the original text bled through under the overlay)
    txt = page.get_text()
    assert "[id]" in txt
    assert txt.count("The quick brown fox") == 1
