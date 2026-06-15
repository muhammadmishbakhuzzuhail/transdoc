"""PaddleOCR engine: maps rec_texts/rec_scores/rec_polys -> Block IR (text + bbox + conf),
without needing paddleocr installed (a fake recognizer is injected)."""

from __future__ import annotations

import io

import pytest

PIL = pytest.importorskip("PIL")
pytest.importorskip("numpy")

from PIL import Image  # noqa: E402

from transdoc.config import Config  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402
from transdoc.ocr.paddle import PADDLE_LANG, PaddleOCREngine  # noqa: E402


class _FakePaddle:
    """Stands in for a PaddleOCR pipeline: predict() returns one OCRResult-like dict."""

    def predict(self, arr):
        return [{
            "rec_texts": ["Hello world", "  ", "second line"],
            "rec_scores": [0.97, 0.5, 0.42],
            "rec_polys": [
                [(10, 20), (110, 20), (110, 45), (10, 45)],
                [(0, 0), (5, 0), (5, 5), (0, 5)],
                [(12, 60), (140, 60), (140, 88), (12, 88)],
            ],
        }]


def _png_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_blocks_from_triples_shared_parser():
    # the in-process and subprocess paths funnel through this; blanks dropped, conf flagged
    from transdoc.ocr.paddle import _blocks_from_triples
    triples = [
        ("Hello", 0.97, [(10, 20), (110, 20), (110, 45), (10, 45)]),
        ("  ", 0.5, [(0, 0), (1, 0), (1, 1), (0, 1)]),
        ("low", 0.3, [(0, 50), (40, 50), (40, 70), (0, 70)]),
    ]
    blocks = _blocks_from_triples(triples, page=2, flag_threshold=0.9)
    assert [b.text for b in blocks] == ["Hello", "low"]
    assert blocks[0].page == 2 and blocks[0].confidence.ocr == 0.97
    assert (blocks[0].bbox.x0, blocks[0].bbox.y1) == (10, 45)
    assert "low_ocr_confidence" in blocks[1].flags and "low_ocr_confidence" not in blocks[0].flags


def test_available_is_bool():
    # construction never raises even without paddle; available reflects whether a runner exists
    eng = PaddleOCREngine()
    assert isinstance(eng.available, bool)


def test_lang_mapping():
    eng = PaddleOCREngine()
    assert eng._lang(Config(target_lang="id", source_lang="de")) == "german"
    assert eng._lang(Config(target_lang="id", source_lang="zh")) == "ch"
    assert eng._lang(Config(target_lang="id", source_lang="hi")) == "hi"   # passthrough
    assert eng._lang(Config(target_lang="id", source_lang="auto")) == "en"  # no image
    assert PADDLE_LANG["ja"] == "japan"


def test_auto_uses_detected_script(monkeypatch):
    import transdoc.ocr.paddle as mod
    eng = PaddleOCREngine()
    monkeypatch.setattr(mod, "detect_script_lang", lambda img: "hi")
    # auto + image -> the script read off the image wins
    assert eng._lang(Config(target_lang="id", source_lang="auto"), img=b"x") == "hi"
    # explicit source ignores detection
    assert eng._lang(Config(target_lang="id", source_lang="ar"), img=b"x") == "ar"


def test_script_to_lang_map():
    from transdoc.ocr.paddle import SCRIPT_TO_LANG
    assert SCRIPT_TO_LANG["Devanagari"] == "hi"
    assert SCRIPT_TO_LANG["Arabic"] == "ar"
    assert SCRIPT_TO_LANG["Cyrillic"] == "ru"
    assert SCRIPT_TO_LANG["Han"] == "ch"


def test_maps_results_to_blocks():
    eng = PaddleOCREngine()
    eng._inproc = True                                    # force in-process path for the fake
    eng._cache["en"] = _FakePaddle()                      # bypass the heavy real init
    cfg = Config(target_lang="id", source_lang="en", flag_threshold=0.9)
    blocks = eng.recognize_image_bytes(_png_bytes(), cfg, page=3)

    assert [b.text for b in blocks] == ["Hello world", "second line"]   # blank dropped
    b0 = blocks[0]
    assert b0.page == 3 and b0.type == BlockType.PARAGRAPH
    assert b0.confidence.source == "ocr" and b0.confidence.ocr == 0.97
    assert (b0.bbox.x0, b0.bbox.y0, b0.bbox.x1, b0.bbox.y1) == (10, 20, 110, 45)
    assert "low_ocr_confidence" not in b0.flags
    # second line is below threshold -> flagged
    assert "low_ocr_confidence" in blocks[1].flags
