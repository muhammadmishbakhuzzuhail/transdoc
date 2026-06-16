"""Translation memory store — exact-match reuse over the shared SQLite database.

Replaces ``translate.memory.PersistentTM`` (which now re-exports this). Same public surface
(``get()`` singleton, ``get_many`` / ``put_many``) so callers and the existing tests are unchanged,
plus optional ``src_lang`` / ``domain`` scoping and provenance/confirmed columns the later PRs use.
Exact-match keeps full parity with the old cache; fuzzy reuse lands in a later PR.
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

from . import db as _db


def _norm(text: str) -> str:
    return " ".join((text or "").strip().split()).lower()


class TMStore:
    """SQLite exact-match TM shared across runs. Engine-agnostic (maximizes reuse). Disable with
    ``TRANSDOC_TM_DISABLE=1``. Thread-safe (WAL + one shared connection guarded by a lock)."""

    _instance: "TMStore | None" = None

    def __init__(self, path: str | Path | None = None):
        self._conn: sqlite3.Connection = _db.connect(path)
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "TMStore | None":
        """Process-wide singleton, or None when disabled via env."""
        if os.environ.get("TRANSDOC_TM_DISABLE") == "1":
            return None
        if cls._instance is None:
            try:
                cls._instance = cls()
            except Exception:
                return None             # never let a TM failure break translation
        return cls._instance

    def get_many(self, sources: list[str], target: str, src_lang: str = "", domain: str = "",
                 ctx: str = "") -> dict[str, str]:
        """Return {source_text: translation} for sources cached for this (target, scope, ctx).
        ctx='' is the plain exact-match cache (NMT); a non-empty ctx is a context-hash bucket."""
        if not sources:
            return {}
        by_norm = {_norm(s): s for s in sources}
        hits: dict[str, str] = {}
        qmarks = ",".join("?" * len(by_norm))
        with self._lock:
            cur = self._conn.execute(
                f"SELECT src_norm, tgt_text FROM tm "
                f"WHERE tgt_lang=? AND src_lang=? AND domain=? AND ctx=? AND src_norm IN ({qmarks})",
                [target, src_lang, domain, ctx, *by_norm.keys()],
            )
            for norm, tgt in cur.fetchall():
                if norm in by_norm:
                    hits[by_norm[norm]] = tgt
        return hits

    def put_many(self, pairs: dict[str, str], target: str, src_lang: str = "", domain: str = "",
                 origin: str = "engine", ctx: str = "") -> None:
        """Store {source_text: translation} for this (target, scope, ctx). Whitespace-only
        translations are skipped. A CONFIRMED row is never overwritten (corrections are immune)."""
        rows = [(_norm(s), s, src_lang, target, domain, ctx, t, origin)
                for s, t in pairs.items() if s.strip() and t and t.strip()]
        self._upsert(rows)

    def get_segments(self, items: list[tuple[str, str]], target: str,
                     src_lang: str = "", domain: str = "") -> dict[tuple[str, str], str]:
        """Per-segment context-hash lookup. items = [(source_text, ctx)]; returns
        {(source_text, ctx): translation} for the ones cached. Used by the doc-context LLM path."""
        if not items:
            return {}
        want = {(_norm(s), c): (s, c) for s, c in items}
        norms = list({n for n, _ in want})
        qmarks = ",".join("?" * len(norms))
        hits: dict[tuple[str, str], str] = {}
        with self._lock:
            cur = self._conn.execute(
                f"SELECT src_norm, ctx, tgt_text FROM tm "
                f"WHERE tgt_lang=? AND src_lang=? AND domain=? AND src_norm IN ({qmarks})",
                [target, src_lang, domain, *norms],
            )
            for norm, ctx, tgt in cur.fetchall():
                key = (norm, ctx)
                if key in want:
                    hits[want[key]] = tgt
        return hits

    def put_segments(self, triples: list[tuple[str, str, str]], target: str,
                     src_lang: str = "", domain: str = "", origin: str = "engine") -> None:
        """Store [(source_text, ctx, translation)] for this (target, scope). Confirmed rows immune."""
        rows = [(_norm(s), s, src_lang, target, domain, c, t, origin)
                for s, c, t in triples if s.strip() and t and t.strip()]
        self._upsert(rows)

    def _upsert(self, rows: list[tuple]) -> None:
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT INTO tm (src_norm, src_text, src_lang, tgt_lang, domain, ctx, tgt_text, "
                "                origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(src_norm, src_lang, tgt_lang, domain, ctx) DO UPDATE SET "
                "  tgt_text=excluded.tgt_text, origin=excluded.origin, "
                "  updated_at=datetime('now') "
                "WHERE tm.confirmed=0",
                rows,
            )
            self._conn.commit()
