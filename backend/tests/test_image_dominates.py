"""PDF scan detection: a page whose only digital text is a title, sitting over a scanned
image holding the real content, must be treated as a scan (OCR'd) — not read as digital and
have its body dropped as a figure. Regression for the UDHR Thai scan: a 47-char English title
over a ~37%-coverage image of the Thai body was classified digital and never OCR'd."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.ingest.detect import _image_dominates  # noqa: E402


def _page(text: str, cover: float):
    """A page (US Letter) with `text` and one image covering `cover` fraction of the area."""
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    if text:
        # textbox wraps, so the full text lands in the layer (insert_text clips one line ~119c)
        p.insert_textbox(fitz.Rect(40, 30, 555, 110), text, fontsize=11)
    area = p.rect.width * p.rect.height
    side = (area * cover) ** 0.5
    pix = fitz.open()
    pix.new_page(width=int(side), height=int(side)).draw_rect(
        fitz.Rect(0, 0, side, side), fill=(0.5, 0.5, 0.5))
    p.insert_image(fitz.Rect(60, 120, 60 + side, 120 + side),
                   pixmap=pix[0].get_pixmap())
    return p


def test_title_over_midsize_scan_is_a_scan():
    # 47-char title + ~37% image -> the Thai-scan case: must be OCR'd
    p = _page("Universal Declaration of Human Rights - Thai", cover=0.37)
    assert _image_dominates(p) is True


def test_full_page_scan_with_sparse_text_is_a_scan():
    p = _page("page 1", cover=0.7)
    assert _image_dominates(p) is True


def test_real_text_page_with_a_figure_is_not_a_scan():
    # a genuine digital page: lots of body text + a mid-size figure -> read, don't OCR
    body = "This is a real paragraph of digital body text. " * 8   # >200 chars
    p = _page(body, cover=0.4)
    assert _image_dominates(p) is False


def test_midsize_image_with_a_real_caption_is_not_a_scan():
    # >120 chars (a real caption/short body) over a 37% image -> not a title-only scan
    cap = "Figure 1. A reasonably long descriptive caption that clearly exceeds the title-only "\
          "threshold so this page is treated as digital, not a scan."
    assert len(cap) > 120
    p = _page(cap, cover=0.37)
    assert _image_dominates(p) is False
