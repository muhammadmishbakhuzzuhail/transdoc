# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Script-routed OCR: engine chain chosen per detected script, escalation reused, graceful when
strong engines are uninstalled (chain collapses to Tesseract)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import BBox, Block, BlockType, Confidence
from transdoc.ocr import router as R


def _blocks(conf, tag):
    return [Block(id=f"{tag}{i}", type=BlockType.PARAGRAPH, page=0, text=f"{tag} line {i}",
                  bbox=BBox(x0=0, y0=i, x1=10, y1=i + 5),
                  confidence=Confidence(source="ocr", ocr=conf)) for i in range(3)]


class _Fake:
    def __init__(self, conf, tag):
        self._b = _blocks(conf, tag)

    def recognize_image_bytes(self, img, cfg, page=0):
        return self._b


CFG = Config(target_lang="id")


def test_unknown_script_uses_default_chain():
    assert R.ROUTING.get("Klingon", R.DEFAULT_CHAIN) == R.DEFAULT_CHAIN


def test_precision_first_chain_order():
    # Latin-ish scripts: Tesseract leads (fast, near-equal accuracy), Paddle escalates.
    for s in ("Latin", "Cyrillic", "Greek", "Arabic", "Hebrew"):
        assert R.ROUTING[s][0] == "tesseract" and R.ROUTING[s][1] == "paddle"
    # Scripts Tesseract is weak at: PaddleOCR (precise + GPU-fast) leads.
    for s in ("Han", "Devanagari", "Thai", "Japanese", "Tamil"):
        assert R.ROUTING[s][0] == "paddle"
    # EasyOCR is always the last-resort fallback (CPU only).
    for chain in [R.DEFAULT_CHAIN, *R.ROUTING.values()]:
        assert chain[-1] == "easyocr"


def test_kannada_does_not_lead_with_paddle():
    # paddle has no Kannada model -> it must not lead (it would OCR Kannada as English at high conf
    # and block escalation to Tesseract, the only engine that can read it).
    assert R.ROUTING["Kannada"][0] == "tesseract"
    assert "paddle" not in R.ROUTING["Kannada"]


def test_routes_by_detected_script(monkeypatch):
    o = R.ScriptRoutedOCR()
    monkeypatch.setattr(R, "detect_script", lambda img: "Han")
    assert o._chain(b"x", CFG) == R.ROUTING["Han"]


def test_explicit_latin_source_keeps_default_chain():
    # An explicit LATIN source trusts Tesseract's lang pack (tesseract-first).
    assert R.ScriptRoutedOCR()._chain(b"x", Config(target_lang="id", source_lang="en")) \
        == R.DEFAULT_CHAIN


def test_explicit_non_latin_source_routes_paddle_first():
    # An explicit NON-Latin source still needs its script chain (paddle-first), not the
    # tesseract-first default — the bug that turned `--source hi/zh` scans to garbage.
    for lang in ("zh", "hi", "ja", "ko"):
        chain = R.ScriptRoutedOCR()._chain(b"x", Config(target_lang="id", source_lang=lang))
        assert chain[0] == "paddle", (lang, chain)


def test_unavailable_engines_collapse_to_tesseract(monkeypatch):
    o = R.ScriptRoutedOCR()
    monkeypatch.setattr(R, "detect_script", lambda img: "Devanagari")
    # tesseract available, the strong engines not
    o._cache = {"tesseract": _Fake(0.9, "tess"), "paddle_vl": None, "paddle": None}
    out = o.recognize_image_bytes(b"x", CFG)
    assert out[0].text.startswith("tess")


def test_escalates_to_strong_when_primary_weak(monkeypatch):
    o = R.ScriptRoutedOCR()
    monkeypatch.setattr(R, "detect_script", lambda img: "Han")
    o._cache = {"tesseract": _Fake(0.2, "tess"), "easyocr": _Fake(0.95, "ez"), "paddle": None}
    out = o.recognize_image_bytes(b"x", CFG)
    assert out[0].text.startswith("ez")          # weak tesseract -> escalated to strong, won
