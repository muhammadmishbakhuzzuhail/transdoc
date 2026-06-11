"""CID-font garbage detection: untrusted digital text is routed to OCR.

Some PDFs embed CID fonts with no ToUnicode CMap, so get_text() returns raw glyph ids
(control chars / mojibake). Those pages must fall back to OCR instead of emitting garbage.
"""

from __future__ import annotations

import fitz

from transdoc.config import Config
from transdoc.extract import pdf as pdfmod
from transdoc.extract.pdf import _looks_garbage, extract
from transdoc.ir import Block, BlockType, Confidence


def test_looks_garbage_detects_control_heavy_text():
    assert _looks_garbage("\x00\x02\x01\x04 \x05 \x08 \x0e \x08\x10\x0f " * 5) is True
    assert _looks_garbage("7X\\zQ\x03QJ{Q\x03WR\x7fQ\x03WK\x9b\x03JL" * 5) is True


def test_looks_garbage_passes_real_scripts():
    assert _looks_garbage("Universal Declaration of Human Rights, preamble and articles.") is False
    assert _looks_garbage("الإعلان العالمي لحقوق الإنسان الديباجة وجميع المواد هنا.") is False
    assert _looks_garbage("世界人权宣言序言以及所有条款都在这里显示出来。") is False
    assert _looks_garbage("short") is False  # too short to judge


class _FakeOCR:
    def recognize_image_bytes(self, img_bytes, cfg, page=0):
        return [Block(id=f"ocr{page}", type=BlockType.PARAGRAPH, page=page,
                      text="recovered via ocr", confidence=Confidence(source="ocr"))]


def test_garbage_page_routes_to_ocr(tmp_path, monkeypatch):
    src = tmp_path / "doc.pdf"
    d = fitz.open()
    d.new_page().insert_text((40, 60), "ignored — forced garbage", fontsize=12)
    d.save(str(src))
    d.close()

    monkeypatch.setattr(pdfmod, "_looks_garbage", lambda text: True)
    monkeypatch.setattr("transdoc.ocr.get_ocr", lambda cfg: _FakeOCR())

    doc = extract(str(src), Config(target_lang="en"))
    assert [b.confidence.source for b in doc.blocks] == ["ocr"]
    assert doc.blocks[0].text == "recovered via ocr"


def test_clean_page_stays_digital(tmp_path, monkeypatch):
    src = tmp_path / "clean.pdf"
    d = fitz.open()
    d.new_page().insert_text((40, 60), "Clean readable English text here.", fontsize=12)
    d.save(str(src))
    d.close()
    # OCR must never be called for a clean page
    monkeypatch.setattr("transdoc.ocr.get_ocr",
                        lambda cfg: (_ for _ in ()).throw(AssertionError("OCR called on clean page")))
    doc = extract(str(src), Config(target_lang="en"))
    assert all(b.confidence.source == "digital" for b in doc.blocks)
