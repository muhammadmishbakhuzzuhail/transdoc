# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Translate hardening: CJK sentence-aware splitting + don't cache whitespace-only translations."""

from __future__ import annotations

from transdoc.translate.google import _split_long


def test_split_prefers_cjk_full_stop():
    # 。 sits past limit//2 so it's chosen as the cut (vs a mid-run space-less split)
    s = "第一句子内容在这里写了很多个字。" + "第二句子继续写更多的内容字符" * 5
    parts = _split_long(s, 30)
    assert len(parts) >= 2
    assert parts[0].endswith("。")          # cut at the sentence mark, not mid-sentence


def test_split_latin_sentence_boundary():
    s = "First long opening sentence here. " + "second part " * 20
    parts = _split_long(s, 50)
    assert parts[0].rstrip().endswith(".")


def test_split_short_text_unchanged():
    assert _split_long("short", 100) == ["short"]


def test_tm_skips_whitespace_only_translation(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "tm.sqlite"))
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    from transdoc.translate.memory import PersistentTM
    PersistentTM._inst = None
    tm = PersistentTM.get()
    tm.put_many({"hello": "   ", "world": "dunia"}, "id")
    got = tm.get_many(["hello", "world"], "id")
    assert "hello" not in got and got.get("world") == "dunia"
