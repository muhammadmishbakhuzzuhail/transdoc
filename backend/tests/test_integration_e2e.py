# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""End-to-end integration: a synthetic multi-element PDF (title, heading, paragraph, list,
table, image) runs through the whole pipeline into several output formats without crashing,
with structure preserved and text translated. Uses the echo engine (no network)."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _rich_pdf(path):
    d = fitz.open()
    pg = d.new_page(width=460, height=620)
    pg.insert_text((40, 50), "Annual Report 2025", fontsize=22)            # title (big)
    pg.insert_text((40, 90), "1 Overview", fontsize=15)                    # numbered heading
    pg.insert_text((40, 120), "This section summarises the year in review and outlook.",
                   fontsize=11)
    pg.insert_text((40, 150), "- First key point about growth", fontsize=11)
    pg.insert_text((40, 168), "- Second key point about costs", fontsize=11)
    # a ruled 2x2 table
    for (x0, y0, x1, y1), t in [((40, 200, 160, 222), "Metric"), ((160, 200, 280, 222), "Value"),
                                ((40, 222, 160, 244), "Revenue"), ((160, 222, 280, 244), "100")]:
        pg.draw_rect(fitz.Rect(x0, y0, x1, y1))
        pg.insert_text((x0 + 4, y0 + 16), t, fontsize=10)
    # an embedded image
    logo = fitz.open()
    logo.new_page(width=60, height=60).draw_rect(fitz.Rect(0, 0, 60, 60), fill=(0.9, 0.3, 0.1))
    pg.insert_image(fitz.Rect(300, 200, 400, 300), pixmap=logo[0].get_pixmap())
    d.save(str(path))


def _cfg(fmt, fidelity=Fidelity.AUTO):
    return Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                  output_format=fmt, fidelity=fidelity, mode=Mode.FULL)


@pytest.mark.parametrize("fmt", [OutputFormat.PDF, OutputFormat.DOCX,
                                 OutputFormat.MARKDOWN, OutputFormat.PLAIN])
def test_rich_pdf_to_every_target_does_not_crash(tmp_path, fmt):
    src = tmp_path / "report.pdf"
    _rich_pdf(src)
    out = tmp_path / f"report.id.{fmt.value}"
    res = run(str(src), _cfg(fmt), out_path=str(out))
    assert out.exists() and out.stat().st_size > 0
    # every translatable block got a translation
    trans = [b for b in res.doc.blocks if b.is_translatable]
    assert trans and all(b.translated for b in trans)


def test_rich_pdf_structure_detected(tmp_path):
    src = tmp_path / "report.pdf"
    _rich_pdf(src)
    res = run(str(src), _cfg(OutputFormat.MARKDOWN), out_path=str(tmp_path / "o.md"))
    types = {b.type for b in res.doc.blocks}
    assert BlockType.TITLE in types or BlockType.HEADING in types
    assert BlockType.LIST_ITEM in types
    assert BlockType.FIGURE in types                       # image captured
    md = (tmp_path / "o.md").read_text(encoding="utf-8")
    assert "[id]" in md and "|" in md                      # translated + a markdown table


def test_markdown_has_translated_table(tmp_path):
    src = tmp_path / "report.pdf"
    _rich_pdf(src)
    run(str(src), _cfg(OutputFormat.MARKDOWN), out_path=str(tmp_path / "o.md"))
    md = (tmp_path / "o.md").read_text(encoding="utf-8")
    assert "[id] Revenue" in md or "[id] Metric" in md     # table cells translated in the grid


def test_layout_opt_in_still_works(tmp_path):
    src = tmp_path / "report.pdf"
    _rich_pdf(src)
    out = tmp_path / "report.layout.pdf"
    run(str(src), _cfg(OutputFormat.PDF, Fidelity.LAYOUT), out_path=str(out))
    assert fitz.open(str(out)).page_count >= 1             # overlay path renders
