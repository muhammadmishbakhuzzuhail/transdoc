# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Unified store TMStore: legacy-cache migration, (src_lang, domain) scoping, confirmed-immunity."""

from __future__ import annotations

import sqlite3

from transdoc.store import db as store_db
from transdoc.store.tm import TMStore


def test_scoping_by_src_lang_and_domain(tmp_path):
    s = TMStore(path=tmp_path / "transdoc.db")
    s.put_many({"bank": "tepi sungai"}, target="id", src_lang="en", domain="geo")
    s.put_many({"bank": "bank"}, target="id", src_lang="en", domain="finance")
    assert s.get_many(["bank"], "id", src_lang="en", domain="geo") == {"bank": "tepi sungai"}
    assert s.get_many(["bank"], "id", src_lang="en", domain="finance") == {"bank": "bank"}
    assert s.get_many(["bank"], "id", src_lang="en", domain="") == {}        # global scope: miss
    assert s.get_many(["bank"], "id", src_lang="de", domain="geo") == {}     # other src: miss


def test_confirmed_row_is_immune_to_engine_overwrite(tmp_path):
    db = tmp_path / "transdoc.db"
    s = TMStore(path=db)
    s.put_many({"cat": "kucing"}, target="id")
    # promote to confirmed directly (the correction path lands in a later PR)
    s._conn.execute("UPDATE tm SET confirmed=1 WHERE src_norm='cat'")
    s._conn.commit()
    s.put_many({"cat": "WRONG"}, target="id", origin="engine")               # engine retry
    assert s.get_many(["cat"], "id") == {"cat": "kucing"}                     # not overwritten


def test_confirmed_translation_scoped_by_src_lang(tmp_path):
    # confirmed_translation accepted src_lang/domain params but the query ignored them, so a
    # correction from a different language pair could leak into the consistency pass.
    s = TMStore(path=tmp_path / "transdoc.db")
    s.put_correction("Total", "Jumlah", "id", src_lang="en")
    assert s.confirmed_translation("Total", "id", src_lang="en") == "Jumlah"
    assert s.confirmed_translation("Total", "id", src_lang="de") is None      # other src: no leak


def test_unconfirmed_row_is_updated_by_engine(tmp_path):
    s = TMStore(path=tmp_path / "transdoc.db")
    s.put_many({"cat": "old"}, target="id")
    s.put_many({"cat": "new"}, target="id")
    assert s.get_many(["cat"], "id") == {"cat": "new"}


def test_segments_context_hash_scoped(tmp_path):
    s = TMStore(path=tmp_path / "transdoc.db")
    s.put_segments([("bank", "CTX_geo", "tepi sungai")], target="id", src_lang="en")
    s.put_segments([("bank", "CTX_fin", "bank")], target="id", src_lang="en")
    assert s.get_segments([("bank", "CTX_geo")], "id", src_lang="en") == {("bank", "CTX_geo"): "tepi sungai"}
    assert s.get_segments([("bank", "CTX_fin")], "id", src_lang="en") == {("bank", "CTX_fin"): "bank"}
    assert s.get_segments([("bank", "CTX_other")], "id", src_lang="en") == {}      # unseen ctx -> miss
    # plain exact-match (ctx='') is a separate bucket, unaffected by the context-hashed rows
    assert s.get_many(["bank"], "id", src_lang="en") == {}


def test_legacy_cache_migrated_on_default_path(tmp_path, monkeypatch):
    # build an old-schema tm.sqlite and point the legacy + default paths at the tmp dir
    legacy = tmp_path / "cache" / "transdoc" / "tm.sqlite"
    legacy.parent.mkdir(parents=True)
    old = sqlite3.connect(str(legacy))
    old.execute("CREATE TABLE tm (k TEXT PRIMARY KEY, translation TEXT NOT NULL)")
    old.execute("INSERT INTO tm VALUES (?, ?)", ("id\x00hello world", "halo dunia"))
    old.commit()
    old.close()
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(legacy))
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "data" / "transdoc.db"))
    conn = store_db.connect()                       # default path -> triggers migration
    row = conn.execute("SELECT tgt_text, tgt_lang, src_lang FROM tm WHERE src_norm='hello world'"
                       ).fetchone()
    assert row == ("halo dunia", "id", "")


def test_concurrent_put_get_is_thread_safe(tmp_path):
    """The store is hit from the anyio threadpool (feedback routes) and the worker thread at once;
    its 'WAL + one shared connection guarded by a lock' claim must hold. Interleave N threads doing
    put_many/get_many and assert no 'database is locked'/'recursive use' error and consistent reads."""
    import threading

    s = TMStore(path=tmp_path / "transdoc.db")
    errors: list[Exception] = []

    def worker(i: int):
        try:
            for j in range(25):
                key = f"term{i}-{j}"
                s.put_many({key: f"val{i}-{j}"}, target="id", src_lang="en")
                got = s.get_many([key], "id", src_lang="en")
                assert got.get(key) == f"val{i}-{j}"
        except Exception as e:                       # noqa: BLE001 — record, fail in main thread
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, f"thread-safety violated: {errors[:3]}"
    # every key from every thread persisted
    assert s.get_many(["term7-24"], "id", src_lang="en").get("term7-24") == "val7-24"
