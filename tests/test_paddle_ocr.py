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


def test_lang_mapping():
    eng = PaddleOCREngine()
    assert eng._lang(Config(target_lang="id", source_lang="de")) == "german"
    assert eng._lang(Config(target_lang="id", source_lang="zh")) == "ch"
    assert eng._lang(Config(target_lang="id", source_lang="hi")) == "hi"   # passthrough
    assert eng._lang(Config(target_lang="id", source_lang="auto")) == "en"
    assert PADDLE_LANG["ja"] == "japan"


def test_maps_results_to_blocks():
    eng = PaddleOCREngine()
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
