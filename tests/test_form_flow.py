"""AcroForm (fillable) PDFs are dense tiny fields the LAYOUT overlay mangles, so with AUTO
fidelity the pipeline reflows them (FLOW) instead. A normal PDF keeps LAYOUT."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _form_pdf(path):
    d = fitz.open()
    p = d.new_page(width=400, height=500)
    p.insert_text((40, 40), "Name and address line for the taxpayer", fontsize=10)
    w = fitz.Widget()
    w.field_name = "f1"
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(40, 60, 360, 78)
    p.add_widget(w)
    d.save(str(path))


def _plain_pdf(path):
    d = fitz.open()
    d.new_page(width=400, height=500).insert_text(
        (40, 40), "Just an ordinary paragraph of digital text on the page.", fontsize=11)
    d.save(str(path))


def test_form_pdf_switches_to_flow(tmp_path):
    src = tmp_path / "form.pdf"
    _form_pdf(src)
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO, mode=Mode.FULL)
    run(str(src), cfg, out_path=str(tmp_path / "o.pdf"))
    assert cfg.fidelity == Fidelity.FLOW          # AcroForm -> reflow


def test_plain_pdf_stays_layout(tmp_path):
    src = tmp_path / "plain.pdf"
    _plain_pdf(src)
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO, mode=Mode.FULL)
    run(str(src), cfg, out_path=str(tmp_path / "o.pdf"))
    assert cfg.fidelity == Fidelity.AUTO          # untouched -> resolves to LAYOUT at render
