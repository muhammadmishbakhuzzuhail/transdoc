# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Corrupt/unreadable input -> clear ValueError, not a raw library crash (audit edge-case)."""

from __future__ import annotations

import pytest

from transdoc.config import Config


def _write(tmp_path, name, data=b"not a real document at all"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)


def test_corrupt_pdf_raises_valueerror(tmp_path):
    pytest.importorskip("fitz")
    from transdoc.extract.pdf import extract
    with pytest.raises(ValueError, match="corrupt PDF"):
        extract(_write(tmp_path, "x.pdf"), Config(target_lang="id"))


def test_corrupt_docx_raises_valueerror(tmp_path):
    pytest.importorskip("docx")
    from transdoc.extract.docx import extract
    with pytest.raises(ValueError, match="corrupt DOCX"):
        extract(_write(tmp_path, "x.docx"), Config(target_lang="id"))
