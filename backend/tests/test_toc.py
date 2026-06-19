# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""PDF outline/bookmarks captured, titles translated, outline rebuilt in output."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, OutputFormat  # noqa: E402
from transdoc.ir import TocEntry  # noqa: E402
from transdoc.pipeline import run  # noqa: E402
from transdoc.regenerate.pdf_out import _apply_pdf_toc  # noqa: E402


def test_pdf_toc_captured_and_rewritten(tmp_path):
    d = fitz.open()
    for _ in range(3):
        p = d.new_page(width=400, height=500)
        p.insert_text((40, 60), "Section heading and body text here to translate.")
    d.set_toc([[1, "Introduction", 1], [1, "Methods", 2], [2, "Setup", 3]])
    src = tmp_path / "s.pdf"
    d.save(str(src))
    d.close()

    out = tmp_path / "o.pdf"
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO,
                               output_format=OutputFormat.PDF), out_path=str(out))
    assert len(res.doc.toc) == 3 and res.doc.toc[0].title == "Introduction"
    # output PDF has an outline of the same size
    assert len(fitz.open(str(out)).get_toc()) == 3


def test_apply_toc_clamps_pages(tmp_path):
    d = fitz.open()
    d.new_page(width=300, height=300)

    class _D:
        toc = [TocEntry(level=1, title="X", page=99, translated="X-id")]
    _apply_pdf_toc(d, _D())
    assert d.get_toc()[0][2] == 1   # page clamped to count
    d.close()
