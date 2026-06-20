# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""DOCX footnotes (separate XML part python-docx ignores) are extracted, translated, and written
back in place — previously silently dropped."""

from __future__ import annotations

import os
import tempfile
import zipfile

import pytest

from transdoc.config import Config

pytest.importorskip("docx")


def _craft_footnote_docx(path):
    from docx import Document as Docx
    base = os.path.join(tempfile.mkdtemp(), "b.docx")
    Docx().save(base)
    fn = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
          '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
          '<w:footnote w:id="1"><w:p><w:r><w:t>Original footnote text</w:t></w:r></w:p></w:footnote>'
          '</w:footnotes>')
    zin = zipfile.ZipFile(base)
    zout = zipfile.ZipFile(path, "w")
    for n in zin.namelist():
        data = zin.read(n)
        if n == "[Content_Types].xml":
            data = data.replace(b"</Types>", b'<Override PartName="/word/footnotes.xml" '
                                b'ContentType="application/vnd.openxmlformats-officedocument.'
                                b'wordprocessingml.footnotes+xml"/></Types>')
        if n == "word/_rels/document.xml.rels":
            data = data.replace(b"</Relationships>", b'<Relationship Id="rId900" Type="http://'
                                b'schemas.openxmlformats.org/officeDocument/2006/relationships/'
                                b'footnotes" Target="footnotes.xml"/></Relationships>')
        zout.writestr(n, data)
    zout.writestr("word/footnotes.xml", fn)
    zout.close()
    zin.close()


def test_footnote_extracted_and_round_tripped(tmp_path):
    from transdoc.extract.docx import extract
    from transdoc.regenerate.docx_inplace import render
    src = tmp_path / "fn.docx"
    _craft_footnote_docx(str(src))
    doc = extract(str(src), Config(target_lang="id"))
    note = next((b for b in doc.notes if "Original footnote" in b.text), None)
    assert note is not None and note.id.startswith("note:footnote:")
    note.translated = "Teks catatan kaki"
    out = tmp_path / "out.docx"
    render(doc, Config(target_lang="id"), str(out))
    ftxt = zipfile.ZipFile(str(out)).read("word/footnotes.xml").decode()
    assert "Teks catatan kaki" in ftxt and "Original footnote text" not in ftxt
    from docx import Document as Docx
    Docx(str(out))   # output is still a valid docx


def _craft_textbox_docx(path):
    from docx import Document as Docx
    base = os.path.join(tempfile.mkdtemp(), "b.docx")
    d = Docx()
    d.add_paragraph("Body paragraph")
    d.save(base)
    tbx = ('<w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
           'xmlns:v="urn:schemas-microsoft-com:vml"><w:r><w:pict><v:shape><v:textbox>'
           '<w:txbxContent><w:p><w:r><w:t>Textbox text here</w:t></w:r></w:p>'
           '</w:txbxContent></v:textbox></v:shape></w:pict></w:r></w:p>')
    zin = zipfile.ZipFile(base)
    zout = zipfile.ZipFile(path, "w")
    for n in zin.namelist():
        data = zin.read(n)
        if n == "word/document.xml":
            data = data.replace(b"</w:body>", tbx.encode() + b"</w:body>")
        zout.writestr(n, data)
    zout.close()
    zin.close()


def test_textbox_extracted_body_untouched_and_round_tripped(tmp_path):
    from transdoc.extract.docx import extract
    from transdoc.regenerate.docx_inplace import render
    src = tmp_path / "tbx.docx"
    _craft_textbox_docx(str(src))
    doc = extract(str(src), Config(target_lang="id"))
    tbx = [b for b in doc.notes if b.id.startswith("note:textbox:")]
    assert len(tbx) == 1 and tbx[0].text == "Textbox text here"
    assert [b.text for b in doc.blocks] == ["Body paragraph"]   # body index-zip unaffected
    tbx[0].translated = "Teks kotak"
    out = tmp_path / "out.docx"
    render(doc, Config(target_lang="id"), str(out))
    docxml = zipfile.ZipFile(str(out)).read("word/document.xml").decode()
    assert "Teks kotak" in docxml and "Textbox text here" not in docxml
    assert "Body paragraph" in docxml                            # body preserved
    from docx import Document as Docx
    Docx(str(out))
