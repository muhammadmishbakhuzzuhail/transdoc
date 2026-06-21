# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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


def lexical_ratio(a: str, b: str) -> float:
    """Character-level similarity (0..1) of two normalized strings. Used both as the fallback fuzzy
    score (no embedder) and as the auto-apply safety gate: a near-1.0 ratio means the strings differ
    only by a few characters, so reusing the past translation is safe once protected tokens match."""
    from difflib import SequenceMatcher
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


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

    def put_correction(self, source: str, corrected: str, target: str,
                       src_lang: str = "", domain: str = "") -> None:
        """Store a human-confirmed segment translation: confirmed=1, origin='correction'. Overrides
        any existing row for the key (corrections are authoritative) and makes it immune to later
        auto-overwrite by an engine result."""
        if not (source and source.strip() and corrected and corrected.strip()):
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO tm (src_norm, src_text, src_lang, tgt_lang, domain, ctx, tgt_text, "
                "                origin, confirmed) VALUES (?, ?, ?, ?, ?, '', ?, 'correction', 1) "
                "ON CONFLICT(src_norm, src_lang, tgt_lang, domain, ctx) DO UPDATE SET "
                "  tgt_text=excluded.tgt_text, origin='correction', confirmed=1, "
                "  updated_at=datetime('now')",
                [_norm(source), source, src_lang, target, domain, corrected],
            )
            self._conn.commit()

    def confirm(self, source: str, target: str, src_lang: str = "", domain: str = "") -> int:
        """Promote an existing engine entry to confirmed=1 (immune to auto-overwrite). Returns the
        number of rows confirmed."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tm SET confirmed=1, updated_at=datetime('now') "
                "WHERE src_norm=? AND tgt_lang=? AND src_lang=? AND domain=?",
                [_norm(source), target, src_lang, domain],
            )
            self._conn.commit()
            return cur.rowcount

    def stats(self) -> dict[str, int]:
        """Row counts: total / confirmed / unconfirmed."""
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM tm").fetchone()[0]
            confirmed = self._conn.execute(
                "SELECT COUNT(*) FROM tm WHERE confirmed=1").fetchone()[0]
        return {"total": total, "confirmed": confirmed, "unconfirmed": total - confirmed}

    def purge(self, unconfirmed_only: bool = True, older_than_days: int | None = None) -> int:
        """Delete TM rows. By default only unconfirmed (confirmed corrections are protected). With
        ``older_than_days`` also restrict to rows last updated before that cutoff. Returns rows deleted."""
        where = ["confirmed=0"] if unconfirmed_only else []
        params: list = []
        if older_than_days is not None:
            where.append("updated_at < datetime('now', ?)")
            params.append(f"-{int(older_than_days)} days")
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM tm{clause}", params)
            self._conn.commit()
            return cur.rowcount

    def confirmed_translation(self, source: str, target: str, src_lang: str = "",
                              domain: str = "") -> str | None:
        """The human-confirmed translation of ``source`` for this target, if any (newest wins).
        Used by the consistency pass to prefer a correction when harmonising duplicates."""
        # Honour src_lang / domain when given (the params existed but the query ignored them, so a
        # confirmed correction from an unrelated language pair / domain could leak into a lookup).
        q = "SELECT tgt_text FROM tm WHERE src_norm=? AND tgt_lang=? AND confirmed=1"
        params: list = [_norm(source), target]
        if src_lang:
            q += " AND src_lang=?"
            params.append(src_lang)
        if domain:
            q += " AND domain=?"
            params.append(domain)
        q += " ORDER BY updated_at DESC LIMIT 1"
        with self._lock:
            row = self._conn.execute(q, params).fetchone()
        return row[0] if row else None

    def export_pairs(self) -> list[dict]:
        """All TM entries as dicts (source/target/src_lang/tgt_lang/domain/confirmed) — for TMX
        export / backup."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT src_text, tgt_text, src_lang, tgt_lang, domain, confirmed FROM tm "
                "ORDER BY src_lang, tgt_lang, domain, src_text")
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def import_pairs(self, rows) -> int:
        """Insert (source, target, src_lang, tgt_lang, domain) tuples — for TMX import. Reuses the
        confirmed-immune upsert; imported rows are origin='import'. Returns the count attempted."""
        triples = [(_norm(s), s, sl, tl, dom, "", t, "import")
                   for s, t, sl, tl, dom in rows if s and s.strip() and t and t.strip()]
        self._upsert(triples)
        return len(triples)

    def fuzzy_search(self, source: str, target: str, src_lang: str = "", domain: str = "",
                     embedder=None, limit: int = 5, min_score: float = 0.5,
                     candidate_cap: int = 500, confirmed_only: bool = False
                     ) -> list[tuple[str, str, float]]:
        """Find past translations whose SOURCE is similar to ``source`` (monolingual). Returns
        ``[(src_text, tgt_text, score)]`` sorted by score desc. Scope: same (target, src_lang,
        domain) — plus global ('') when a domain is given. ``confirmed_only`` restricts to
        human-confirmed corrections (the feedback-flywheel few-shot source). Scoring: cosine via
        ``embedder`` if provided, else :func:`lexical_ratio`. Candidates are token-prefiltered then
        capped to bound the work on a large TM (personal-scale: a linear scan over the scoped rows)."""
        if not source or not source.strip():
            return []
        # src_lang/domain wildcard '': engine rows are stored unscoped (src_lang='', domain=''),
        # corrections carry the real language — match both so fuzzy reuses either.
        langs = {src_lang, ""}
        domains = {domain, ""} if domain else {""}
        lq = ",".join("?" * len(langs))
        dq = ",".join("?" * len(domains))
        conf = " AND confirmed=1" if confirmed_only else ""
        with self._lock:
            cur = self._conn.execute(
                f"SELECT src_text, tgt_text FROM tm "
                f"WHERE tgt_lang=? AND src_lang IN ({lq}) AND domain IN ({dq}) "
                f"AND tgt_text<>''{conf}",
                [target, *langs, *domains],
            )
            rows = cur.fetchall()
        if not rows:
            return []
        # Token-overlap prefilter: keep rows sharing at least one token with the query (cheap, drops
        # obviously-unrelated rows), then cap so scoring stays bounded.
        q_tokens = set(_norm(source).split())
        prefiltered = [(s, t) for s, t in rows
                       if s != source and q_tokens & set(_norm(s).split())]
        if not prefiltered:
            return []
        prefiltered = prefiltered[:candidate_cap]
        srcs = [s for s, _ in prefiltered]
        if embedder is not None:
            scores = embedder.similarity(source, srcs)
        else:
            scores = [lexical_ratio(source, s) for s in srcs]
        scored = [(s, t, sc) for (s, t), sc in zip(prefiltered, scores) if sc >= min_score]
        scored.sort(key=lambda r: r[2], reverse=True)
        return scored[:limit]

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
