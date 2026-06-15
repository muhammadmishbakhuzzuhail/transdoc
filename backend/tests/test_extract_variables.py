"""Richer extraction variables: DOCX merged-cell dedup, PDF metadata + page rotation capture."""

from __future__ import annotations

import pytest

from transdoc.config import Config


def test_docx_merged_cell_text_not_duplicated(tmp_path):
    docx = pytest.importorskip("docx")
    from transdoc.extract.docx import extract

    d = docx.Document()
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text = "Merged Header"
    t.cell(0, 0).merge(t.cell(0, 1))          # horizontal merge -> shared <w:tc>
    t.cell(1, 0).text = "a"
    t.cell(1, 1).text = "b"
    p = tmp_path / "m.docx"
    d.save(str(p))

    doc = extract(str(p), Config(target_lang="id"))
    tbl = next(b for b in doc.blocks if b.table)
    texts = [c.text for c in tbl.table.rows[0]]
    assert texts.count("Merged Header") == 1   # appears once, not duplicated across the merge
    assert [c.text for c in tbl.table.rows[1]] == ["a", "b"]


def test_pdf_metadata_and_rotation_captured(tmp_path):
    fitz = pytest.importorskip("fitz")
    from transdoc.extract.pdf import extract

    d = fitz.open()
    d.set_metadata({"title": "My Doc", "author": "Tester"})
    pg = d.new_page(width=595, height=842)
    pg.insert_text((50, 100), "Some body text on a rotated page here.")
    pg.set_rotation(90)
    path = tmp_path / "r.pdf"
    d.save(str(path))
    d.close()

    doc = extract(str(path), Config(target_lang="id"))
    assert doc.metadata.get("title") == "My Doc"
    assert doc.metadata.get("author") == "Tester"
    assert doc.page_rotation.get(0) == 90      # rotation flagged


def test_pdf_line_spacing_geometric():
    """PDF has no line-spacing attribute; derive it from baseline gaps (gap/font_size)."""
    import tempfile

    import fitz

    from transdoc.config import Config
    from transdoc.extract.pdf import extract
    d = fitz.open()
    p = d.new_page(width=400, height=300)
    for i in range(4):                                   # font 12, gap 18 -> spacing 1.5
        p.insert_text((40, 60 + i * 18), f"Body line {i} with several words here.", fontsize=12)
    f = tempfile.mktemp(suffix=".pdf")
    d.save(f)
    d.close()
    blk = next(b for b in extract(f, Config(target_lang="id")).blocks if b.text.strip())
    assert blk.style.line_spacing == 1.5


def test_line_spacing_single_line_none():
    from transdoc.extract.pdf import _line_spacing
    assert _line_spacing([{"spans": [{"origin": (0, 100)}]}], 12) is None   # one line -> None
    assert _line_spacing([], 12) is None
