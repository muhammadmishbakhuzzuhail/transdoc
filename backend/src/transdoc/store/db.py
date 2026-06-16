"""SQLite connection, schema + versioned migrations, and one-time import of the legacy TM cache.

One file holds the whole persistence layer (translation memory now; glossary + corrections in
later PRs). It lives under the XDG *data* dir — not the cache dir — because glossary/corrections
are user assets that must survive a cache clear. Location overridable with ``TRANSDOC_DB_PATH``.
See GLOSSARY-TM-FEEDBACK-SPEC.md.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 2


def default_db_path() -> Path:
    """``TRANSDOC_DB_PATH`` if set, else ``$XDG_DATA_HOME/transdoc/transdoc.db`` (data, not cache)."""
    env = os.environ.get("TRANSDOC_DB_PATH")
    if env:
        return Path(env)
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "transdoc" / "transdoc.db"


def _legacy_tm_path() -> Path:
    """Where the pre-store exact-match cache lived (``translate.memory.PersistentTM``)."""
    env = os.environ.get("TRANSDOC_TM_PATH")
    if env:
        return Path(env)
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "transdoc" / "tm.sqlite"


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the database at ``path`` (default: ``default_db_path()``) and apply
    the schema/migrations. When ``path`` is None (the real, default DB) the legacy ``tm.sqlite``
    cache is imported the first time the ``tm`` table is empty; an explicit ``path`` (tests,
    project-local DBs) skips that import so it stays isolated."""
    is_default = path is None
    p = default_db_path() if is_default else Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    if is_default:
        _import_legacy_tm(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent, forward-only migrations gated on ``PRAGMA user_version``."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 1:
        # v1: translation memory. Forward columns (provenance, confirmed, embedding) are created
        # now so later PRs need no ALTER; only exact-match get/put use them in this PR.
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tm (
              id         INTEGER PRIMARY KEY,
              src_norm   TEXT NOT NULL,
              src_text   TEXT NOT NULL,
              src_lang   TEXT NOT NULL DEFAULT '',
              tgt_lang   TEXT NOT NULL,
              domain     TEXT NOT NULL DEFAULT '',
              tgt_text   TEXT NOT NULL,
              origin     TEXT NOT NULL DEFAULT 'engine',
              confirmed  INTEGER NOT NULL DEFAULT 0,
              engine     TEXT,
              quality    REAL,
              hits       INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              embedding  BLOB,
              UNIQUE(src_norm, src_lang, tgt_lang, domain)
            );
            """
        )
        conn.execute("PRAGMA user_version=1")
    if version < 2:
        # v2: add `ctx` to the TM key for context-hash caching of the document-context LLM (Area A2).
        # NMT rows use ctx=''; an LLM row is keyed by a hash of its source neighbour window, so the
        # same segment in a different context caches separately. The v1 table-level
        # UNIQUE(src_norm,src_lang,tgt_lang,domain) would forbid that, so the table is rebuilt with
        # ctx in the UNIQUE; existing rows migrate with ctx='' (identity preserved).
        conn.executescript(
            """
            CREATE TABLE tm_v2 (
              id         INTEGER PRIMARY KEY,
              src_norm   TEXT NOT NULL,
              src_text   TEXT NOT NULL,
              src_lang   TEXT NOT NULL DEFAULT '',
              tgt_lang   TEXT NOT NULL,
              domain     TEXT NOT NULL DEFAULT '',
              ctx        TEXT NOT NULL DEFAULT '',
              tgt_text   TEXT NOT NULL,
              origin     TEXT NOT NULL DEFAULT 'engine',
              confirmed  INTEGER NOT NULL DEFAULT 0,
              engine     TEXT,
              quality    REAL,
              hits       INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL DEFAULT (datetime('now')),
              updated_at TEXT NOT NULL DEFAULT (datetime('now')),
              embedding  BLOB,
              UNIQUE(src_norm, src_lang, tgt_lang, domain, ctx)
            );
            INSERT INTO tm_v2 (id, src_norm, src_text, src_lang, tgt_lang, domain, tgt_text,
                               origin, confirmed, engine, quality, hits, created_at, updated_at,
                               embedding)
              SELECT id, src_norm, src_text, src_lang, tgt_lang, domain, tgt_text, origin,
                     confirmed, engine, quality, hits, created_at, updated_at, embedding FROM tm;
            DROP TABLE tm;
            ALTER TABLE tm_v2 RENAME TO tm;
            """
        )
        conn.execute("PRAGMA user_version=2")
    conn.commit()
    # guard: code expecting a newer schema than the file should fail loudly, not corrupt data.
    if conn.execute("PRAGMA user_version").fetchone()[0] > _SCHEMA_VERSION:
        raise RuntimeError("transdoc.db is newer than this build expects; upgrade transdoc")


def _import_legacy_tm(conn: sqlite3.Connection) -> None:
    """Copy entries from the old ``tm.sqlite`` (schema ``tm(k, translation)`` keyed
    ``"<target>\\x00<norm-source>"``) the first time the new ``tm`` table is empty. One-shot; never
    overwrites existing rows. Legacy rows have no recorded source language -> ``src_lang=''``."""
    if conn.execute("SELECT 1 FROM tm LIMIT 1").fetchone():
        return
    legacy = _legacy_tm_path()
    if not legacy.exists() or legacy == _db_file(conn):
        return
    try:
        old = sqlite3.connect(str(legacy))
        rows = old.execute("SELECT k, translation FROM tm").fetchall()
        old.close()
    except Exception:
        return                                  # missing/incompatible legacy file -> skip silently
    out = []
    for k, tr in rows:
        if not k or "\x00" not in k or not tr:
            continue
        target, norm = k.split("\x00", 1)
        out.append((norm, norm, "", target, "", tr))
    if out:
        conn.executemany(
            "INSERT OR IGNORE INTO tm (src_norm, src_text, src_lang, tgt_lang, domain, tgt_text) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            out,
        )
        conn.commit()


def _db_file(conn: sqlite3.Connection) -> Path | None:
    row = conn.execute("PRAGMA database_list").fetchone()
    return Path(row[2]) if row and row[2] else None
