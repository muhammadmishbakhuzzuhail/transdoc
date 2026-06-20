# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Detection degrades gracefully on pathological PDFs: encrypted -> clear error, corrupt -> clear
error, instead of a raw PyMuPDF crash deep in extraction."""

from __future__ import annotations

import fitz
import pytest

from transdoc.ingest.detect import detect


def test_encrypted_pdf_clear_error(tmp_path):
    p = tmp_path / "enc.pdf"
    d = fitz.open()
    d.new_page()
    d.save(str(p), encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    d.close()
    with pytest.raises(ValueError, match="password-protected"):
        detect(str(p))


def test_corrupt_pdf_clear_error(tmp_path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.7\nnot really a pdf\n%%EOF")
    with pytest.raises(ValueError, match="unreadable or corrupt"):
        detect(str(p))
