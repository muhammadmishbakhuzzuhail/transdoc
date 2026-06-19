# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Translation memory: in-memory dedupe + persistent SQLite cache."""

from __future__ import annotations

from transdoc.translate.memory import PersistentTM, TranslationMemory


def test_dedupe_collapses_repeats_and_maps_back():
    tm = TranslationMemory()
    texts = ["Hello", "world", "hello", "WORLD ", "new"]
    unique, idx_map = tm.dedupe(texts)
    # case/whitespace-insensitive normalization collapses Hello/hello and world/WORLD
    assert unique == ["Hello", "world", "new"]
    assert idx_map == [0, 1, 0, 1, 2]
    # scatter back reproduces original length
    assert [unique[i] for i in idx_map] == ["Hello", "world", "Hello", "world", "new"]


def test_in_memory_lookup_is_normalized():
    tm = TranslationMemory()
    tm.add("Good Morning", "Selamat Pagi")
    assert tm.lookup("good   morning") == "Selamat Pagi"
    assert tm.lookup("absent") is None


def test_persistent_tm_roundtrip(tmp_path):
    db = tmp_path / "tm.sqlite"
    ptm = PersistentTM(path=db)
    ptm.put_many({"cat": "kucing", "dog": "anjing"}, target="id")
    hits = ptm.get_many(["cat", "dog", "fish"], target="id")
    assert hits == {"cat": "kucing", "dog": "anjing"}


def test_persistent_tm_is_target_scoped(tmp_path):
    ptm = PersistentTM(path=tmp_path / "tm.sqlite")
    ptm.put_many({"cat": "kucing"}, target="id")
    assert ptm.get_many(["cat"], target="id") == {"cat": "kucing"}
    assert ptm.get_many(["cat"], target="fr") == {}  # different target -> miss


def test_persistent_tm_survives_reopen(tmp_path):
    db = tmp_path / "tm.sqlite"
    PersistentTM(path=db).put_many({"cat": "kucing"}, target="id")
    # a fresh connection to the same file still sees the row
    assert PersistentTM(path=db).get_many(["cat"], target="id") == {"cat": "kucing"}


def test_persistent_tm_normalizes_source_key(tmp_path):
    ptm = PersistentTM(path=tmp_path / "tm.sqlite")
    ptm.put_many({"Hello World": "Halo Dunia"}, target="id")
    assert ptm.get_many(["hello   world"], target="id") == {"hello   world": "Halo Dunia"}


def test_persistent_tm_disabled_via_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    PersistentTM._instance = None
    assert PersistentTM.get() is None
