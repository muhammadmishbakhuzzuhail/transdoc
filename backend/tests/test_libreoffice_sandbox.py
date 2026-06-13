"""Legacy-format conversion via LibreOffice is sandboxed: isolated throwaway profile, CPU +
output-size rlimits, and the profile is cleaned up. Skipped where soffice isn't installed."""

from __future__ import annotations

import glob
import shutil

import pytest

pytest.importorskip("docx")

from transdoc.ingest.detect import convert_to_docx  # noqa: E402

_HAS_SOFFICE = shutil.which("soffice") is not None


def _odt(path):
    odf = pytest.importorskip("odf.opendocument")
    from odf.text import P
    d = odf.OpenDocumentText()
    d.text.addElement(P(text="Hello from a legacy document."))
    d.save(str(path))


@pytest.mark.skipif(not _HAS_SOFFICE, reason="soffice not installed")
def test_conversion_produces_docx_and_cleans_profile(tmp_path):
    src = tmp_path / "in.odt"
    _odt(src)
    before = set(glob.glob("/tmp/transdoc_lo_*"))
    out = convert_to_docx(src, tmp_path / "out")
    assert out.exists() and out.stat().st_size > 0
    # no leaked throwaway profile dir
    assert set(glob.glob("/tmp/transdoc_lo_*")) <= before


def test_signature_accepts_timeout():
    # the hardened signature exposes a timeout knob (callers can tighten it)
    import inspect
    params = inspect.signature(convert_to_docx).parameters
    assert "timeout" in params and params["timeout"].default == 90
