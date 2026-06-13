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
