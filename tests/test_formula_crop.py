"""Math fidelity: formula blocks are placed as a pixel-perfect crop of the source region
(fractions / super- & subscripts survive), not as get_text-flattened linear text."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat  # noqa: E402
from transdoc.extract.pdf import extract  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _formula_pdf(path):
    d = fitz.open()
    pg = d.new_page(width=400, height=300)
    pg.insert_text((40, 40), "Some ordinary body paragraph text to translate here on page.",
                   fontsize=11)
    # a line that the formula heuristic detects (math op + lone variables, few words)
    pg.insert_text((40, 90), "a = b + c ∑ d √ e", fontsize=11)
    d.save(str(path))


def test_formula_detected_and_cropped(tmp_path):
    src = tmp_path / "f.pdf"
    _formula_pdf(src)
    doc = extract(str(src), Config(target_lang="id", output_format=OutputFormat.PDF))
    assert any(b.type == BlockType.FORMULA for b in doc.blocks)    # heuristic fired

    out = tmp_path / "f.id.pdf"
    run(str(src), Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                         output_format=OutputFormat.PDF, fidelity=Fidelity.RECONSTRUCT,
                         mode=Mode.FULL), out_path=str(out))
    # the formula region is placed as an image crop -> output page carries an image
    assert sum(len(p.get_images()) for p in fitz.open(str(out))) >= 1
