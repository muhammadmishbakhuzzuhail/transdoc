"""PDF inline runs: capture mixed-style spans from a block + render styled <span> in pdf html."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.extract.pdf import _runs_from_spans, extract  # noqa: E402
from transdoc.config import Config  # noqa: E402
from transdoc.ir import BlockType, Run, Style  # noqa: E402
from transdoc.regenerate.pdf_out import _runs_html  # noqa: E402


def test_runs_from_spans_groups_mixed():
    lines = [{"spans": [
        {"text": "normal ", "size": 11.0, "flags": 0, "color": 0},
        {"text": "bold", "size": 11.0, "flags": 16, "color": 0},   # bold flag
    ]}]
    runs = _runs_from_spans(lines)
    assert len(runs) == 2 and runs[1].style.bold and runs[1].text.startswith("bold")


def test_runs_from_spans_uniform_returns_empty():
    lines = [{"spans": [{"text": "all same", "size": 11.0, "flags": 0, "color": 0}]}]
    assert _runs_from_spans(lines) == []


def test_runs_html_renders_spans():
    html = _runs_html([Run(text="x", style=Style(bold=True)),
                       Run(text="y", style=Style(superscript=True))])
    assert "font-weight:bold" in html and "vertical-align:super" in html


def test_pdf_extract_captures_runs(tmp_path):
    d = fitz.open()
    p = d.new_page(width=400, height=400)
    p.insert_text((40, 60), "plain ", fontname="helv", fontsize=11)
    p.insert_text((80, 60), "BOLD", fontname="hebo", fontsize=11)  # bold face
    path = tmp_path / "m.pdf"
    d.save(str(path))
    d.close()
    doc = extract(str(path), Config(target_lang="id"))
    paras = [b for b in doc.blocks if b.type == BlockType.PARAGRAPH and b.runs]
    assert paras and any(r.style.bold for b in paras for r in b.runs)
