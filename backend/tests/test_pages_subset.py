"""--pages selection: the LAYOUT overlay output contains ONLY the selected pages, not a mix
of translated + untranslated original pages."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _three_page_pdf(path):
    d = fitz.open()
    for i in range(3):
        d.new_page(width=300, height=400).insert_text(
            (40, 60), f"Page {i} has some ordinary digital text to translate here.",
            fontsize=11)
    d.save(str(path))


def test_pages_subset_output(tmp_path):
    src = tmp_path / "doc.pdf"
    _three_page_pdf(src)
    out = tmp_path / "o.pdf"
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.LAYOUT,
                 mode=Mode.FULL, pages="2")
    run(str(src), cfg, out_path=str(out))
    assert fitz.open(str(out)).page_count == 1        # only the selected page


def test_all_pages_when_unset(tmp_path):
    src = tmp_path / "doc.pdf"
    _three_page_pdf(src)
    out = tmp_path / "o.pdf"
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.LAYOUT, mode=Mode.FULL)
    run(str(src), cfg, out_path=str(out))
    assert fitz.open(str(out)).page_count == 3
