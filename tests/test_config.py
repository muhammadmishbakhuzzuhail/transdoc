"""Config defaults + fidelity resolution + target requirement."""

from __future__ import annotations

import pytest

from transdoc.config import Config, Engine, Fidelity, OutputFormat


def test_default_engine_is_free_fallback_chain():
    assert Config(target_lang="id").engine == Engine.FALLBACK


def test_require_target_raises_when_unset():
    with pytest.raises(ValueError):
        Config().require_target()
    assert Config(target_lang="id").require_target() == "id"


def test_auto_fidelity_is_flow_even_for_pdf_to_pdf():
    # reflow is the readable default; the visual overlay is opt-in via -f layout
    cfg = Config(target_lang="id", output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO)
    assert cfg.resolve_fidelity(source_is_pdf=True) == Fidelity.FLOW


def test_auto_fidelity_same_as_source_pdf_is_flow():
    cfg = Config(target_lang="id", output_format=OutputFormat.SAME, fidelity=Fidelity.AUTO)
    assert cfg.resolve_fidelity(source_is_pdf=True) == Fidelity.FLOW


def test_auto_fidelity_pdf_to_docx_is_flow():
    cfg = Config(target_lang="id", output_format=OutputFormat.DOCX, fidelity=Fidelity.AUTO)
    assert cfg.resolve_fidelity(source_is_pdf=True) == Fidelity.FLOW


def test_explicit_layout_is_respected():
    cfg = Config(target_lang="id", fidelity=Fidelity.LAYOUT)
    assert cfg.resolve_fidelity(source_is_pdf=True) == Fidelity.LAYOUT


def test_roundtrip_formats_present_in_enum():
    values = {f.value for f in OutputFormat}
    assert {"pptx", "xlsx", "epub", "srt", "vtt"}.issubset(values)
