"""EasyOCR engine: result parsing (polygon->bbox, conf) + language selection. The model itself
is heavy/optional, so these cover the pure glue (parse_results, _langs)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import BlockType
from transdoc.ocr.easyocr_engine import EasyOCREngine, parse_results


def test_parse_polygon_to_bbox_and_conf():
    results = [
        ([[10, 20], [110, 20], [110, 50], [10, 50]], "मानव अधिकारों", 0.65),
        ([[10, 60], [90, 60], [90, 80], [10, 80]], "Hindi", 0.95),
    ]
    blocks = parse_results(results, page=0)
    assert len(blocks) == 2
    b = blocks[0]
    assert b.type == BlockType.PARAGRAPH and b.text == "मानव अधिकारों"
    assert (b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1) == (10, 20, 110, 50)
    assert b.confidence.source == "ocr" and abs(b.confidence.ocr - 0.65) < 1e-6


def test_parse_skips_empty_and_malformed():
    results = [
        ([[0, 0], [1, 0], [1, 1], [0, 1]], "   ", 0.9),   # blank -> skipped
        ("garbage",),                                     # malformed -> skipped
        ([[0, 0], [2, 0], [2, 2], [0, 2]], "ok", 0.8),
    ]
    blocks = parse_results(results)
    assert [b.text for b in blocks] == ["ok"]


def test_langs_from_detected_script():
    e = EasyOCREngine()
    cfg = Config(target_lang="id", source_lang="auto")
    assert e._langs(cfg, "Devanagari") == ["hi", "en"]
    assert e._langs(cfg, "Han") == ["ch_sim", "en"]
    assert e._langs(cfg, "Latin") == ["en"]              # english alone, not duplicated


def test_langs_from_explicit_source():
    e = EasyOCREngine()
    assert e._langs(Config(target_lang="id", source_lang="zh"), None) == ["ch_sim", "en"]
    assert e._langs(Config(target_lang="id", source_lang="en"), None) == ["en"]


def test_registry_exposes_easyocr():
    from transdoc.ocr import router as R
    assert "easyocr" in R._BUILDERS                      # registered in the chains regardless
    assert "easyocr" in R.ROUTING["Devanagari"]
    # builder returns an engine when installed, None otherwise — never raises
    built = R._build_easyocr()
    import importlib.util
    if importlib.util.find_spec("easyocr") is not None:
        assert built is not None
    else:
        assert built is None
