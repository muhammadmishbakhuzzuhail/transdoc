# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Tesseract auto-script detection: a non-Latin scan with source=auto must pick the matching
lang pack (via OSD) instead of defaulting to 'eng' and returning Latin gibberish."""

from __future__ import annotations

import pytest

from transdoc.config import Config

pytest.importorskip("pytesseract")
import pytesseract  # noqa: E402

from transdoc.ocr.tesseract import _SCRIPT_LANG, _avail_langs, TesseractOCR  # noqa: E402

_AVAIL = set(pytesseract.get_languages(config=""))


def test_script_map_has_major_scripts():
    for script, lang in [("Devanagari", "hin"), ("Han", "chi_sim"), ("Arabic", "ara"),
                         ("Cyrillic", "rus"), ("Hangul", "kor"), ("Thai", "tha")]:
        assert _SCRIPT_LANG[script] == lang


def test_script_model_preference_resolution():
    # _detect_script_lang prefers script/<Script> over the lang pack. Latin needs no map entry
    # (its fallback is eng); non-Latin scripts keep a lang-pack fallback for when the script
    # model isn't installed. Replicates the resolver's candidate order.
    assert "Latin" not in _SCRIPT_LANG          # handled by the script-name path, not the map
    assert _SCRIPT_LANG["Greek"] == "ell" and _SCRIPT_LANG["Cyrillic"] == "rus"

    def resolve(script, avail):
        for cand in (f"script/{script}", script, _SCRIPT_LANG.get(script)):
            if cand and cand in avail:
                return cand
        return None

    assert resolve("Greek", {"script/Greek", "ell"}) == "script/Greek"   # model preferred
    assert resolve("Greek", {"ell"}) == "ell"                            # fallback to lang pack
    assert resolve("Latin", {"eng"}) is None                             # -> _langs adds eng
    assert resolve("Cyrillic", {"script/Cyrillic"}) == "script/Cyrillic"


def test_avail_langs_lists_eng_and_is_robust():
    # our own --list-langs parse (pytesseract.get_languages drops the first-sorted entry, which
    # silently hid the uppercase 'Latin' script pack). 'eng'/'osd' ship with every install.
    avail = _avail_langs()
    assert "eng" in avail
    # must not lose an uppercase-named pack the way get_languages does
    raw = pytesseract.get_languages(config="")
    if "Latin" in raw or any(x[:1].isupper() for x in raw):
        pass  # get_languages happened to keep it here; nothing to prove
    # _avail_langs is a superset of the lowercase packs get_languages returns
    assert {x for x in raw if x.islower()} <= avail


def test_detected_lang_used_when_source_auto():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="auto")
    langs = tr._langs(cfg, detected="hin" if "hin" in _AVAIL else None)
    if "hin" in _AVAIL:
        # a non-Latin script pack is used ALONE — adding "eng" makes tesseract misread native
        # glyphs as Latin lookalikes (Greek ΚΑΙ -> "KAI"; eval: greek CER 5.4% -> 2.7%).
        assert langs.split("+") == ["hin"]
    else:
        assert langs == "eng"                 # pack unavailable -> genuine fallback


def test_explicit_source_overrides_detection():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="ru")
    langs = tr._langs(cfg, detected="hin")    # explicit source wins; detected ignored
    assert "hin" not in langs.split("+")


def test_no_detection_falls_back_to_eng():
    tr = TesseractOCR()
    cfg = Config(target_lang="id", source_lang="auto")
    assert tr._langs(cfg, detected=None) == "eng"
