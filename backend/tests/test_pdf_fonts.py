# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""PDF output is self-contained for non-Latin scripts.

PyMuPDF (>=1.26) ships a broad bundled Noto set and embeds the shaped glyphs into the output PDF,
so non-Latin text renders on any viewer with no host fonts installed. This guards against a future
PyMuPDF regression silently reintroducing tofu (the old documented limitation). We simulate a host
with NO system fonts by pointing fontconfig at an empty config, then assert each script both inks
pixels and embeds a font in the produced PDF.
"""

from __future__ import annotations

import io
import os
import tempfile

import pytest

fitz = pytest.importorskip("fitz")

# One sample per high-tofu writing system the renderer must cover without host fonts.
_SAMPLES = {
    "Devanagari": "नमस्ते दुनिया",
    "Arabic": "مرحبا بالعالم",
    "Han": "你好世界",
    "Hebrew": "שלום עולם",
    "Tamil": "வணக்கம் உலகம்",
    "Thai": "สวัสดีชาวโลก",
}


@pytest.fixture
def _no_system_fonts(monkeypatch):
    """Disable fontconfig discovery so only PyMuPDF's own bundled fonts are available."""
    empty = tempfile.mkdtemp()
    cfg = os.path.join(empty, "fonts.conf")
    with open(cfg, "w") as f:
        f.write('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">'
                "<fontconfig></fontconfig>")
    monkeypatch.setenv("FONTCONFIG_FILE", cfg)
    monkeypatch.setenv("FONTCONFIG_PATH", empty)
    yield


def _render(text: str) -> tuple[list, int]:
    doc = fitz.open()
    page = doc.new_page(width=320, height=120)
    page.insert_htmlbox(fitz.Rect(10, 10, 310, 110), f"<div>{text}</div>")
    buf = io.BytesIO()
    doc.save(buf, garbage=4)
    doc.close()
    d = fitz.open("pdf", buf.getvalue())
    fonts = d.get_page_fonts(0)
    pix = d[0].get_pixmap()
    ink = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 250)
    d.close()
    return fonts, ink


@pytest.mark.parametrize("script,text", list(_SAMPLES.items()))
def test_non_latin_pdf_self_contained(_no_system_fonts, script, text):
    fonts, ink = _render(text)
    assert ink > 20, f"{script}: no glyphs rendered (tofu) without host fonts"
    assert fonts, f"{script}: no font embedded in the output PDF"
