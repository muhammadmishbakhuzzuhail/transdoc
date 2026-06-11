"""Google language-code normalization (no network — only the code mapping is exercised)."""

from __future__ import annotations

from transdoc.translate.google import GoogleTranslator


def test_chinese_maps_to_google_code():
    g = GoogleTranslator()
    assert g._code("zh") == "zh-CN"
    assert g._code("zh-Hant") == "zh-TW"


def test_legacy_codes_remapped():
    g = GoogleTranslator()
    assert g._code("he") == "iw"   # Hebrew
    assert g._code("jv") == "jw"   # Javanese


def test_auto_and_passthrough():
    g = GoogleTranslator()
    assert g._code("auto") == "auto"
    assert g._code(None) == "auto"
    assert g._code("id") == "id"   # unmapped code passes through unchanged


def test_make_falls_back_to_auto_on_bad_source():
    # a bad/unsupported detected source code must not crash — retry with auto-detect
    g = GoogleTranslator()
    calls = []

    class _Eng:
        def __init__(self, source, target):
            calls.append(source)
            if source != "auto":
                raise ValueError(f"no support for source {source}")

    g._G = _Eng
    g._make("tn", "id")           # "tn" rejected -> falls back to auto
    assert calls == ["tn", "auto"]
