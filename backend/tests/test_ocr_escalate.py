"""AUTO OCR escalation: clean Tesseract pages are kept; low-confidence pages escalate to the
stronger engine and the more-confident result wins."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence


def _blocks(conf, tag):
    return [Block(id=f"{tag}{i}", type=BlockType.PARAGRAPH, page=0, text=f"{tag} line {i}",
                  bbox=BBox(x0=0, y0=i, x1=10, y1=i + 5),
                  confidence=Confidence(source="ocr", ocr=conf)) for i in range(3)]


class _Fake:
    def __init__(self, conf, tag):
        self._b = _blocks(conf, tag)

    def recognize_image_bytes(self, img, cfg, page=0):
        return self._b


def _engine(tess_conf, strong_conf):
    from transdoc.ocr.auto import EscalatingOCR
    e = EscalatingOCR()
    e._tess = _Fake(tess_conf, "tess")
    e._strong_tried = True
    e._strong = _Fake(strong_conf, "paddle") if strong_conf is not None else None
    return e


CFG = Config(target_lang="id")


def test_high_confidence_keeps_tesseract():
    e = _engine(tess_conf=0.92, strong_conf=0.99)
    out = e.recognize_image_bytes(b"", CFG)
    assert out[0].text.startswith("tess")          # never escalated


def test_low_confidence_escalates_to_stronger():
    e = _engine(tess_conf=0.30, strong_conf=0.95)
    out = e.recognize_image_bytes(b"", CFG)
    assert out[0].text.startswith("paddle")        # escalated, stronger won


def test_escalation_keeps_better_of_the_two():
    # low tess, but the stronger engine does even worse -> keep tesseract
    e = _engine(tess_conf=0.30, strong_conf=0.10)
    out = e.recognize_image_bytes(b"", CFG)
    assert out[0].text.startswith("tess")


def test_no_strong_engine_falls_back_to_tesseract():
    e = _engine(tess_conf=0.30, strong_conf=None)   # paddle not installed
    out = e.recognize_image_bytes(b"", CFG)
    assert out[0].text.startswith("tess")
