# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""In-place ODT translation: an .odt source -> same-as-source mutates the document, swapping
text while keeping headings, lists and tables. Also: docx/odt same-as-source map correctly."""

from __future__ import annotations

import pytest

pytest.importorskip("odf.opendocument")

from odf import teletype  # noqa: E402
from odf.opendocument import OpenDocumentText, load  # noqa: E402
from odf.table import Table, TableCell, TableRow  # noqa: E402
from odf.text import H, List, ListItem, P  # noqa: E402

from transdoc.config import Config, Engine, Mode, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _make_odt(path):
    d = OpenDocumentText()
    d.text.addElement(H(outlinelevel=1, text="Report Title"))
    d.text.addElement(P(text="A paragraph of body content here."))
    lst = List()
    item = ListItem()
    item.addElement(P(text="First bullet point"))
    lst.addElement(item)
    d.text.addElement(lst)
    t = Table(name="T1")
    for vals in (["Name", "Value"], ["Alpha", "One"]):
        row = TableRow()
        for v in vals:
            c = TableCell()
            c.addElement(P(text=v))
            row.addElement(c)
        t.addElement(row)
    d.text.addElement(t)
    d.save(str(path))


def test_odt_inplace_keeps_structure_and_swaps_text(tmp_path):
    src = tmp_path / "doc.odt"
    _make_odt(src)
    out = tmp_path / "doc.id.odt"
    run(str(src), Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                         output_format=OutputFormat.SAME, mode=Mode.FULL), out_path=str(out))

    o, t = load(str(src)), load(str(out))
    assert len(o.getElementsByType(H)) == len(t.getElementsByType(H))
    assert len(o.getElementsByType(Table)) == len(t.getElementsByType(Table))
    assert teletype.extractText(t.getElementsByType(H)[0]).startswith("[id] Report Title")
    cell0 = t.getElementsByType(Table)[0].getElementsByType(TableCell)[0]
    assert teletype.extractText(cell0) == "[id] Name"     # table cell translated in place


def test_same_as_source_maps_odt_and_docx():
    from transdoc.regenerate import _EXT_TO_FORMAT
    assert _EXT_TO_FORMAT[".odt"] == OutputFormat.ODT
    assert _EXT_TO_FORMAT[".docx"] == OutputFormat.DOCX
