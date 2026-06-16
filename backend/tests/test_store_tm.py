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


def test_unconfirmed_row_is_updated_by_engine(tmp_path):
    s = TMStore(path=tmp_path / "transdoc.db")
    s.put_many({"cat": "old"}, target="id")
    s.put_many({"cat": "new"}, target="id")
    assert s.get_many(["cat"], "id") == {"cat": "new"}


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
