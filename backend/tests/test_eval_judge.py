# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""LLM-as-judge helpers — the non-API parts (render + extraction-summary + schema). The judge
call itself needs ANTHROPIC_API_KEY and is not exercised here; `anthropic` is imported lazily so
this module loads without the [llm] extra (CI installs core+dev+formats+api only)."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from scripts import eval_judge  # noqa: E402


def test_render_image_passthrough(tmp_path):
    """An image source is read as-is with its real media type (no rasterisation)."""
    from PIL import Image
    p = tmp_path / "scan.png"
    Image.new("RGB", (40, 30), "white").save(p)
    data, media = eval_judge.render_to_png(str(p))
    assert media == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"          # real PNG bytes


def test_render_pdf_first_page(tmp_path):
    """A PDF source rasterises its first page to PNG."""
    d = fitz.open()
    d.new_page(width=300, height=400).insert_text((40, 60), "Hello", fontsize=14)
    d.new_page()                                       # 2nd page must be ignored
    out = tmp_path / "doc.pdf"
    d.save(str(out))
    d.close()
    data, media = eval_judge.render_to_png(str(out))
    assert media == "image/png"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_rejects_unknown_type(tmp_path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"nope")
    with pytest.raises(ValueError):
        eval_judge.render_to_png(str(p))


def test_extracted_blocks_page1_only(tmp_path):
    """extracted_blocks renders 'TYPE: text' lines for page 1 of the extraction."""
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((60, 80), "A heading line", fontsize=16)
    p.insert_text((60, 120), "Some body text on the first page.", fontsize=11)
    out = tmp_path / "two.pdf"
    d.new_page().insert_text((60, 80), "Second page text", fontsize=12)
    d.save(str(out))
    d.close()
    summary = eval_judge.extracted_blocks(str(out))
    assert "heading line" in summary.lower() or "body text" in summary.lower()
    assert "second page" not in summary.lower()       # page 1 only
    assert ":" in summary                              # "TYPE: text" shape


def test_schema_is_strict_and_complete():
    s = eval_judge._SCHEMA
    assert s["additionalProperties"] is False
    for key in ("text_fidelity", "completeness", "structure", "reading_order_ok",
                "missing", "hallucinated", "notes"):
        assert key in s["properties"] and key in s["required"]
