# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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


def test_none_result_retries_then_recovers(monkeypatch):
    # a throttled endpoint answering None on the first call must be retried, not silently
    # passed through as source text.
    g = GoogleTranslator()
    seq = [None, None, "halo"]

    class _Eng:
        def __init__(self, source, target):
            pass

        def translate(self, chunk):
            return seq.pop(0)

    g._G = _Eng
    monkeypatch.setattr("transdoc.translate.google.time.sleep", lambda *_: None)
    assert g._translate_one("hello", "en", "id") == "halo"


def test_persistent_none_raises_not_silent_source(monkeypatch):
    # if every attempt fails, raise (so the fallback chain runs) instead of keeping source.
    g = GoogleTranslator()

    class _Eng:
        def __init__(self, source, target):
            pass

        def translate(self, chunk):
            return None

    g._G = _Eng
    monkeypatch.setattr("transdoc.translate.google.time.sleep", lambda *_: None)
    import pytest
    with pytest.raises(Exception):
        g._translate_one("hello", "en", "id")


def test_throttle_enforces_min_interval(monkeypatch):
    # anti-ban pacing: with a min interval set, consecutive calls are spaced apart
    import importlib
    import time

    monkeypatch.setenv("GOOGLE_MIN_INTERVAL", "0.05")
    import transdoc.translate.google as g
    importlib.reload(g)
    try:
        t0 = time.monotonic()
        for _ in range(3):
            g._throttle()
        assert time.monotonic() - t0 >= 0.09          # ~2 gaps of 0.05s
    finally:
        monkeypatch.delenv("GOOGLE_MIN_INTERVAL", raising=False)
        importlib.reload(g)


def test_throttle_off_by_default(monkeypatch):
    import importlib
    import time

    monkeypatch.delenv("GOOGLE_MIN_INTERVAL", raising=False)
    import transdoc.translate.google as g
    importlib.reload(g)
    t0 = time.monotonic()
    for _ in range(5):
        g._throttle()
    assert time.monotonic() - t0 < 0.02               # no-op when unset


def test_batch_concurrency_preserves_order_and_blanks(monkeypatch):
    """Concurrent batch translation keeps 1:1 input order and passes blank segments through."""
    from transdoc.config import Config
    g = GoogleTranslator()
    # avoid network: translate = uppercase marker, no HTTP
    monkeypatch.setattr(g, "_translate_one", lambda t, s, tg: f"X:{t}")
    texts = [f"seg{i}" for i in range(20)] + ["", "  "]
    out = g.translate_batch(texts, Config(target_lang="id"), src="en")
    assert out[:20] == [f"X:seg{i}" for i in range(20)]   # order preserved
    assert out[20] == "" and out[21] == "  "              # blanks untouched (not sent)
