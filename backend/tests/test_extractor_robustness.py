# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Corrupt office/PDF inputs raise a clean ValueError (not a raw library traceback), matching
the docx/pdf behavior — so the pipeline can report 'unreadable or corrupt' uniformly."""

from __future__ import annotations

import pytest

from transdoc.config import Config


def _junk(tmp_path, name):
    p = tmp_path / name
    p.write_bytes(b"this is not a real office file \x00\x01\x02")
    return str(p)


def test_pptx_corrupt_raises_valueerror(tmp_path):
    pytest.importorskip("pptx")
    from transdoc.extract.pptx import extract
    with pytest.raises(ValueError, match="corrupt PPTX"):
        extract(_junk(tmp_path, "x.pptx"), Config(target_lang="id"))


def test_xlsx_corrupt_raises_valueerror(tmp_path):
    pytest.importorskip("openpyxl")
    from transdoc.extract.xlsx import extract
    with pytest.raises(ValueError, match="corrupt XLSX"):
        extract(_junk(tmp_path, "x.xlsx"), Config(target_lang="id"))


def test_epub_corrupt_raises_valueerror(tmp_path):
    pytest.importorskip("ebooklib")
    from transdoc.extract.epub import extract
    with pytest.raises(ValueError, match="corrupt EPUB"):
        extract(_junk(tmp_path, "x.epub"), Config(target_lang="id"))


def test_odt_corrupt_raises_valueerror(tmp_path):
    pytest.importorskip("odf")
    from transdoc.extract.odt import extract
    with pytest.raises(ValueError, match="corrupt ODT"):
        extract(_junk(tmp_path, "x.odt"), Config(target_lang="id"))
