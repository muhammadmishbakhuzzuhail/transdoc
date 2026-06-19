# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Positioned PDF reconstruction (the DeepL approach): the output keeps the SOURCE page
count, page size, block positions and images — only the text is translated. This is the
PDF->PDF AUTO default."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _multi_page_us_letter(path, pages=3):
    d = fitz.open()
    logo = fitz.open()
    logo.new_page(width=50, height=50).draw_rect(fitz.Rect(0, 0, 50, 50), fill=(1, 0, 0))
    for i in range(pages):
        pg = d.new_page(width=612, height=792)            # US Letter, not A4
        pg.insert_text((40, 40 + 0), f"Heading on page {i}", fontsize=16)
        pg.insert_text((40, 80), "Some body text to translate on this page here.", fontsize=11)
        if i == 0:
            pg.insert_image(fitz.Rect(400, 60, 480, 140), pixmap=logo[0].get_pixmap())
    d.save(str(path))


def test_reconstruct_preserves_page_count_and_size(tmp_path):
    src = tmp_path / "doc.pdf"
    _multi_page_us_letter(src, pages=3)
    out = tmp_path / "doc.id.pdf"
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO, mode=Mode.FULL)
    run(str(src), cfg, out_path=str(out))

    assert cfg.resolve_fidelity(True) == Fidelity.RECONSTRUCT
    di, do = fitz.open(str(src)), fitz.open(str(out))
    assert do.page_count == di.page_count                 # 3 -> 3
    assert (round(do[0].rect.width), round(do[0].rect.height)) == (612, 792)   # US Letter kept
    assert sum(len(p.get_images()) for p in do) >= 1      # image re-placed


def test_reconstruct_places_text_near_original_position(tmp_path):
    src = tmp_path / "doc.pdf"
    _multi_page_us_letter(src, pages=1)
    out = tmp_path / "doc.id.pdf"
    run(str(src), Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                         output_format=OutputFormat.PDF, mode=Mode.FULL), out_path=str(out))
    # heading was at y~40 in the source; the translated heading lands in the top region
    page = fitz.open(str(out))[0]
    d = page.get_text("dict")
    ys = [ln["bbox"][1] for blk in d["blocks"] for ln in blk.get("lines", [])
          if any("Heading" in sp["text"] for sp in ln.get("spans", []))]
    assert ys and min(ys) < 120                           # near the top, not reflowed to A4 flow
