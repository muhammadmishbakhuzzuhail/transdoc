"""Glossary store — persisted term→rendering enforcement over the shared SQLite database (PR-2).

A glossary entry pins how a source term is rendered in the target, document-wide and across runs,
so a name/term never drifts and a once-corrected term stays fixed. Entries are scoped per
``(src_lang, tgt_lang)`` + domain and carry a precedence tier:

    locked  >  user  >  confirmed  >  auto

(``locked`` is the explicit "never touch this" pin; ``user`` = added by hand; ``confirmed`` = promoted
from a correction in PR-3; ``auto`` = a mined suggestion the user accepted). Domain-specific entries
outrank global ('') ones at the same tier. ``resolve`` flattens all of that into a single
``{term: rendering}`` map (highest tier wins) plus the set of locked terms, which the translator
applies via protect→restore-target.

The ephemeral ``-g`` flag is NOT stored here — it is layered on top as a per-run "user" tier by the
caller (``translate/base.py``), still below ``locked``.

``glossary_suggestions`` is the pending queue that auto-mining (and later fuzzy TM) writes into; it
is surfaced to the user but never applied straight from the table. Disable persistence with
``TRANSDOC_TM_DISABLE=1`` (same switch as the TM, so tests get a clean slate).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path

from . import db as _db

# Precedence rank for the origin tier (higher applied last → wins on a term collision).
_ORIGIN_RANK = {"auto": 0, "confirmed": 1, "user": 2}


def _filter_clause(src_lang: str | None, tgt_lang: str | None,
                   domain: str | None) -> tuple[str, list]:
    """Build an optional ``WHERE`` clause + params for the list queries."""
    where, params = [], []
    if src_lang:
        where.append("src_lang=?")
        params.append(src_lang)
    if tgt_lang:
        where.append("tgt_lang=?")
        params.append(tgt_lang)
    if domain is not None:
        where.append("domain=?")
        params.append(domain)
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    return clause, params


class GlossaryStore:
    """SQLite-backed glossary shared across runs. Thread-safe (WAL + one connection + a lock)."""

    _instance: "GlossaryStore | None" = None

    def __init__(self, path: str | Path | None = None):
        self._conn: sqlite3.Connection = _db.connect(path)
        self._lock = threading.Lock()

    @classmethod
    def get(cls) -> "GlossaryStore | None":
        """Process-wide singleton, or None when persistence is disabled via env."""
        if os.environ.get("TRANSDOC_TM_DISABLE") == "1":
            return None
        if cls._instance is None:
            try:
                cls._instance = cls()
            except Exception:
                return None             # never let a glossary failure break translation
        return cls._instance

    # --- resolution (read path used by the translator) -----------------------------------------

    def resolve(self, src_lang: str, tgt_lang: str,
                domain: str = "") -> tuple[dict[str, str], set[str]]:
        """Flatten the scoped entries into ``({term: rendering}, locked_terms)``.

        Highest precedence wins per term: ``locked > user > confirmed > auto``, and within a tier a
        domain-specific entry beats the global ('') one. With a domain, both that domain and global
        are considered (no cross-domain borrowing); with no/auto domain, only global."""
        if not src_lang or not tgt_lang:
            return {}, set()
        domains = ["", domain] if domain else [""]
        qmarks = ",".join("?" * len(set(domains)))
        with self._lock:
            cur = self._conn.execute(
                f"SELECT term, rendering, origin, locked, domain FROM glossary "
                f"WHERE src_lang=? AND tgt_lang=? AND domain IN ({qmarks})",
                [src_lang, tgt_lang, *set(domains)],
            )
            rows = cur.fetchall()
        # Sort ascending by precedence so a plain dict overwrite leaves the winner last.
        rows.sort(key=lambda r: (r[3], _ORIGIN_RANK.get(r[2], 0), 1 if r[4] else 0))
        merged: dict[str, str] = {}
        locked: dict[str, bool] = {}
        for term, rendering, _origin, is_locked, _dom in rows:
            merged[term] = rendering
            locked[term] = bool(is_locked)
        return merged, {t for t, lk in locked.items() if lk}

    # --- management (CLI / programmatic) -------------------------------------------------------

    def add(self, term: str, rendering: str, src_lang: str, tgt_lang: str,
            domain: str = "", locked: bool = False, origin: str = "user") -> None:
        """Upsert a glossary entry. Re-adding a term updates its rendering/lock/origin."""
        if not (term and term.strip() and rendering and rendering.strip()):
            return
        with self._lock:
            self._conn.execute(
                "INSERT INTO glossary (src_lang, tgt_lang, domain, term, rendering, origin, locked) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(src_lang, tgt_lang, domain, term) DO UPDATE SET "
                "  rendering=excluded.rendering, origin=excluded.origin, locked=excluded.locked",
                [src_lang, tgt_lang, domain, term, rendering, origin, 1 if locked else 0],
            )
            self._conn.commit()

    def remove(self, term: str, src_lang: str, tgt_lang: str, domain: str = "") -> int:
        """Delete an entry. Returns the number of rows removed."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM glossary WHERE src_lang=? AND tgt_lang=? AND domain=? AND term=?",
                [src_lang, tgt_lang, domain, term],
            )
            self._conn.commit()
            return cur.rowcount

    def list(self, src_lang: str | None = None, tgt_lang: str | None = None,
             domain: str | None = None) -> list[dict]:
        """List entries, optionally filtered by language pair / domain, newest scope first."""
        clause, params = _filter_clause(src_lang, tgt_lang, domain)
        with self._lock:
            cur = self._conn.execute(
                "SELECT src_lang, tgt_lang, domain, term, rendering, origin, locked "
                f"FROM glossary{clause} ORDER BY src_lang, tgt_lang, domain, term",
                params,
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --- suggestions (pending queue: auto-mining + later fuzzy) --------------------------------

    def add_suggestions(self, items: list[tuple[str, str]], src_lang: str, tgt_lang: str,
                        domain: str = "", source_kind: str = "auto") -> None:
        """Record (term, rendering) suggestions. Existing (scope, term) rows are left untouched —
        a suggestion is a no-op once already present; promotion to a real entry is PR-3."""
        rows = [(src_lang, tgt_lang, domain, t, r, source_kind)
                for t, r in items if t and t.strip() and r and r.strip()]
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR IGNORE INTO glossary_suggestions "
                "(src_lang, tgt_lang, domain, term, rendering, source_kind) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._conn.commit()

    def list_suggestions(self, src_lang: str | None = None, tgt_lang: str | None = None,
                         domain: str | None = None) -> list[dict]:
        clause, params = _filter_clause(src_lang, tgt_lang, domain)
        with self._lock:
            cur = self._conn.execute(
                "SELECT src_lang, tgt_lang, domain, term, rendering, source_kind "
                f"FROM glossary_suggestions{clause} ORDER BY src_lang, tgt_lang, domain, term",
                params,
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # --- interop (TSV + JSON) ------------------------------------------------------------------

    def export(self, path: str | Path, src_lang: str | None = None,
               tgt_lang: str | None = None) -> int:
        """Write entries to ``.json`` (list of objects) or ``.tsv`` (src⇥tgt⇥domain⇥term⇥rendering⇥
        origin⇥locked). Returns the count written."""
        entries = self.list(src_lang, tgt_lang)
        p = Path(path)
        if p.suffix.lower() == ".json":
            p.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            header = "src_lang\ttgt_lang\tdomain\tterm\trendering\torigin\tlocked"
            lines = [header] + [
                "\t".join(str(e[c]) for c in
                          ("src_lang", "tgt_lang", "domain", "term", "rendering", "origin", "locked"))
                for e in entries
            ]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return len(entries)

    def import_(self, path: str | Path) -> int:
        """Load entries from a ``.json`` or ``.tsv`` file written by :meth:`export` (or hand-made).
        Each row upserts via :meth:`add`. Returns the count imported."""
        p = Path(path)
        if not p.exists():
            return 0
        rows: list[dict] = []
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return 0
            if isinstance(data, list):
                rows = [r for r in data if isinstance(r, dict)]
        else:
            lines = p.read_text(encoding="utf-8").splitlines()
            if not lines:
                return 0
            cols = lines[0].split("\t")
            for line in lines[1:]:
                if line.strip():
                    rows.append(dict(zip(cols, line.split("\t"))))
        n = 0
        for r in rows:
            term, rendering = r.get("term", ""), r.get("rendering", "")
            src, tgt = r.get("src_lang", ""), r.get("tgt_lang", "")
            if not (term and rendering and src and tgt):
                continue
            self.add(term, rendering, src, tgt, domain=r.get("domain", "") or "",
                     locked=str(r.get("locked", "")) in ("1", "True", "true"),
                     origin=r.get("origin", "user") or "user")
            n += 1
        return n
