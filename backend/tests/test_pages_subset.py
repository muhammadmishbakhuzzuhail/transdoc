# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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


def test_pages_subset_reconstruct_keeps_right_page(tmp_path):
    # RECONSTRUCT may insert spill pages, so output index != source page. --pages must select by
    # SOURCE page (it was trimming the wrong pages once any content spilled).
    src = tmp_path / "doc.pdf"
    _three_page_pdf(src)
    out = tmp_path / "o.pdf"
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.RECONSTRUCT,
                 mode=Mode.FULL, pages="2")
    run(str(src), cfg, out_path=str(out))
    o = fitz.open(str(out))
    assert o.page_count == 1
    assert "Page 1" in o[0].get_text()      # source page index 1 == "Page 1" text; correct page kept
    o.close()
