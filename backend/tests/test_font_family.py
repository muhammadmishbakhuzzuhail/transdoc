# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Source font family is mapped to a CSS generic (serif/sans-serif/monospace) so a thin serif
source renders serif, not a heavy sans default. The exact face isn't embeddable here."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, OutputFormat  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402


def _pdf_with_font(path, fontname, text):
    d = fitz.open()
    pg = d.new_page(width=400, height=300)
    pg.insert_text((40, 60), text, fontname=fontname, fontsize=12)
    d.save(str(path))


@pytest.mark.parametrize("fontname,expected", [
    ("Times-Roman", "serif"),
    ("Helvetica", "sans-serif"),
    ("Courier", "monospace"),
])
def test_font_family_generic(tmp_path, fontname, expected):
    src = tmp_path / "f.pdf"
    _pdf_with_font(src, fontname, "Some body text to classify by font here.")
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.PDF))
    body = [b for b in doc.blocks if b.is_translatable][0]
    assert body.style.font == expected
