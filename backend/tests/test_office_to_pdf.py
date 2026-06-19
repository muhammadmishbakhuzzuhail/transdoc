# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""DOCX/PPTX -> PDF via LibreOffice headless (industry standard), keeping native layout instead
of reflowing to A4. Falls back to the flow renderer when soffice is unavailable (e.g. CI)."""

from __future__ import annotations

import shutil

import pytest

from transdoc.config import Config, OutputFormat
from transdoc.ir import BBox, Block, BlockType, Cell, Confidence, Document, Table

docx = pytest.importorskip("docx")

_HAS_SOFFICE = bool(shutil.which("soffice") or shutil.which("libreoffice"))


def test_office_to_pdf_none_for_pdf_source():
    from transdoc.regenerate import _office_to_pdf
    d = Document(source_path="x.pdf", mime="application/pdf")
    assert _office_to_pdf(d, Config(target_lang="id"), "/tmp/_x.pdf") is None


def _make_docx(path):
    dd = docx.Document()
    dd.add_heading("Title Here", level=1)
    dd.add_paragraph("A body paragraph.")
    t = dd.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Name"
    t.cell(0, 1).text = "Value"
    dd.save(str(path))


def test_docx_to_pdf_produces_valid_pdf(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.docx import extract
    from transdoc.regenerate import regenerate
    src = tmp_path / "in.docx"
    _make_docx(src)
    doc = extract(str(src), Config(target_lang="id"))
    for b in doc.blocks:                 # fake translations (no network)
        b.translated = (b.text or "") + " X"
        if b.table:
            for row in b.table.rows:
                for c in row:
                    c.translated = (c.text or "") + " X"
    out = tmp_path / "out.pdf"
    regenerate(doc, Config(target_lang="id", output_format=OutputFormat.PDF), str(out))
    assert out.exists()
    r = fitz.open(str(out))
    txt = "".join(p.get_text() for p in r)
    r.close()
    assert "Title Here X" in txt                       # translated content present in the PDF
    # cleanup soffice temp dirs the renderer registered
    import shutil as _sh
    for d in doc.tmp_dirs:
        _sh.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(not _HAS_SOFFICE, reason="needs LibreOffice")
def test_docx_to_pdf_uses_soffice_layout(tmp_path):
    # with soffice present the table grid survives (native render), not a flat reflow
    from transdoc.ir import Document as Doc
    from transdoc.regenerate import _office_to_pdf
    src = tmp_path / "s.docx"
    _make_docx(src)
    d = Doc(source_path=str(src), mime="docx")
    d.blocks = [Block(id="t", type=BlockType.TABLE, bbox=BBox(x0=0, y0=0, x1=1, y1=1),
                      table=Table(rows=[[Cell(text="Name"), Cell(text="Value")]]),
                      confidence=Confidence())]
    out = tmp_path / "s.pdf"
    res = _office_to_pdf(d, Config(target_lang="id"), str(out))
    assert res == str(out) and out.exists()
    import shutil as _sh
    for x in d.tmp_dirs:
        _sh.rmtree(x, ignore_errors=True)
