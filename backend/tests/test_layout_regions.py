# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Layout-model integration: a detected non-text region drops the text blocks inside it and
adds a crop_region block (rendered as a verbatim source crop). Uses a fake detector — no
paddle needed in CI."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config  # noqa: E402
from transdoc.extract import pdf as pdf_extract  # noqa: E402
from transdoc.ir import BBox, Block, BlockType, Confidence, Document  # noqa: E402
from transdoc.layout.paddle_layout import Region  # noqa: E402


class _FakeDetector:
    def detect(self, page):
        # one "image" region covering the top half of a 400x600 page
        return [Region("image", 0, 0, 400, 300)]


def test_text_in_region_dropped_and_crop_added(monkeypatch):
    monkeypatch.setattr("transdoc.layout.get_detector", lambda name: _FakeDetector())

    d = fitz.open()
    d.new_page(width=400, height=600)
    doc = Document(source_path="x.pdf", mime="application/pdf", page_count=1)
    doc.page_sizes = {0: (400.0, 600.0)}
    inside = Block(id="in", type=BlockType.PARAGRAPH, page=0, text="label inside the figure",
                   bbox=BBox(x0=50, y0=100, x1=200, y1=120), confidence=Confidence(source="digital"))
    outside = Block(id="out", type=BlockType.PARAGRAPH, page=0, text="body text below figure",
                    bbox=BBox(x0=50, y0=400, x1=350, y1=430), confidence=Confidence(source="digital"))
    doc.blocks = [inside, outside]

    pdf_extract._apply_layout(d, doc, Config(target_lang="id", layout="paddle"))

    ids = [b.id for b in doc.blocks]
    assert "out" in ids                  # body text kept
    assert "in" not in ids               # label inside the image region dropped
    crops = [b for b in doc.blocks if b.crop_region]
    assert len(crops) == 1 and crops[0].type == BlockType.FIGURE   # region added as a crop


def test_ocr_page_skipped(monkeypatch):
    # OCR pages carry pixel bboxes (not points) -> layout filtering is skipped for them
    monkeypatch.setattr("transdoc.layout.get_detector", lambda name: _FakeDetector())
    d = fitz.open()
    d.new_page(width=400, height=600)
    doc = Document(source_path="x.pdf", mime="application/pdf", page_count=1)
    b = Block(id="o", type=BlockType.PARAGRAPH, page=0, text="ocr text",
              bbox=BBox(x0=10, y0=10, x1=100, y1=30), confidence=Confidence(source="ocr"))
    doc.blocks = [b]
    pdf_extract._apply_layout(d, doc, Config(target_lang="id", layout="paddle"))
    assert [x.id for x in doc.blocks] == ["o"]    # untouched


class _FormulaDetector:
    """A big display equation + a tiny inline formula on the same page."""

    def detect(self, page):
        return [
            Region("formula", 218, 464, 393, 490),   # display eq -> crop
            Region("formula", 380, 392, 391, 402),    # inline $d_k$ (11x10 pt) -> keep as text
        ]


def test_inline_formula_kept_display_cropped_and_tail_dropped(monkeypatch):
    monkeypatch.setattr("transdoc.layout.get_detector", lambda name: _FormulaDetector())
    d = fitz.open()
    d.new_page(width=595, height=842)
    doc = Document(source_path="x.pdf", mime="application/pdf", page_count=1)
    doc.page_sizes = {0: (595.0, 842.0)}
    # prose carrying the inline formula (long -> protected even though it overlaps the tiny box)
    prose = Block(id="prose", type=BlockType.PARAGRAPH, page=0,
                  text="of dimension dk, and values of dimension dv, we compute the products",
                  bbox=BBox(x0=300, y0=388, x1=520, y1=405), confidence=Confidence(source="digital"))
    eq = Block(id="eq", type=BlockType.PARAGRAPH, page=0, text="Attention(Q,K,V)=softmax(QKT",
               bbox=BBox(x0=220, y0=465, x1=377, y1=483), confidence=Confidence(source="digital"))
    tail = Block(id="tail", type=BlockType.PARAGRAPH, page=0, text="√dk )V (1)",
                 bbox=BBox(x0=358, y0=473, x1=505, y1=491), confidence=Confidence(source="digital"))
    doc.blocks = [prose, eq, tail]

    pdf_extract._apply_layout(d, doc, Config(target_lang="id", layout="paddle"))
    ids = [b.id for b in doc.blocks]
    assert "prose" in ids                 # long prose with inline math kept (not overwritten)
    assert "eq" not in ids                # equation body inside the display crop dropped
    assert "tail" not in ids              # short ragged tail straddling the crop edge dropped
    crops = [b for b in doc.blocks if b.crop_region]
    assert len(crops) == 1                # only the DISPLAY formula cropped, inline one skipped


def test_subprocess_detector_parses_regions(monkeypatch):
    """SubprocessLayoutDetector shells out to an isolated paddle interpreter and reads the
    regions back from the JSON file (out_path is argv index 4)."""
    import json
    import subprocess
    import types

    from transdoc.layout.paddle_layout import Region, SubprocessLayoutDetector

    def fake_run(cmd, capture_output, text, timeout=None):
        with open(cmd[4], "w") as fh:
            json.dump({"0": [["table", 1, 2, 3, 4]], "3": [["formula", 5, 6, 7, 8]]}, fh)
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    det = SubprocessLayoutDetector("/fake/python")
    res = det.detect_pages(types.SimpleNamespace(name="x.pdf"), [0, 3])
    assert res[0] == [Region("table", 1, 2, 3, 4)]
    assert res[3][0].label == "formula"


def test_get_detector_falls_back_to_subprocess(monkeypatch, tmp_path):
    """With no in-process paddle but TRANSDOC_LAYOUT_PYTHON set, get_detector delegates."""
    import transdoc.layout as layout_mod
    from transdoc.layout.paddle_layout import SubprocessLayoutDetector

    py = tmp_path / "python"
    py.write_text("")
    monkeypatch.setenv("TRANSDOC_LAYOUT_PYTHON", str(py))
    monkeypatch.setattr(layout_mod.importlib.util, "find_spec", lambda name: None)
    det = layout_mod.get_detector("paddle")
    assert isinstance(det, SubprocessLayoutDetector)
    assert det.python_exe == str(py)
