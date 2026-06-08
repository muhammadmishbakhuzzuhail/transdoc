"""Translation memory — exact-match reuse for consistency + fewer engine calls.

Identical source segments translate once and reuse everywhere (a document repeats headers,
labels, table cells). This both enforces consistency and cuts cost/latency. Adapted from the
prior project's reuse index, trimmed to the high-value exact-match path.

Two layers:
- ``TranslationMemory``  : in-memory, per-run dedupe (cuts repeats within one document).
- ``PersistentTM``       : SQLite-backed, cross-document/cross-user cache. This is what keeps
  a free Google-web-endpoint service under the rate limit — a segment translated once for any
  user is never sent to Google again. Keyed on (target_lang, normalized source).
"""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path


def _norm(text: str) -> str:
    return " ".join((text or "").strip().split()).lower()


def _default_db_path() -> Path:
    env = os.environ.get("TRANSDOC_TM_PATH")
    if env:
        return Path(env)
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "transdoc" / "tm.sqlite"


class PersistentTM:
    """SQLite exact-match cache shared across runs. Engine-agnostic by design (maximizes
    reuse): a segment's translation for a given target language is cached once. Disable with
    TRANSDOC_TM_DISABLE=1. Thread-safe (WAL + one shared connection guarded by a lock)."""

    _instance: "PersistentTM | None" = None

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS tm (k TEXT PRIMARY KEY, translation TEXT NOT NULL)"
        )
        self._conn.commit()

    @classmethod
    def get(cls) -> "PersistentTM | None":
        """Process-wide singleton, or None if disabled via env."""
        if os.environ.get("TRANSDOC_TM_DISABLE") == "1":
            return None
        if cls._instance is None:
            try:
                cls._instance = cls()
            except Exception:
                return None  # never let TM failure break translation
        return cls._instance

    @staticmethod
    def _key(source: str, target: str) -> str:
        return f"{target}\x00{_norm(source)}"

    def get_many(self, sources: list[str], target: str) -> dict[str, str]:
        """Return {source_text: translation} for sources already cached for this target."""
        if not sources:
            return {}
        keys = {self._key(s, target): s for s in sources}
        hits: dict[str, str] = {}
        with self._lock:
            cur = self._conn.cursor()
            qmarks = ",".join("?" * len(keys))
            cur.execute(f"SELECT k, translation FROM tm WHERE k IN ({qmarks})", list(keys))
            for k, tr in cur.fetchall():
                hits[keys[k]] = tr
        return hits

    def put_many(self, pairs: dict[str, str], target: str) -> None:
        """Store {source_text: translation} for this target. Empty values are skipped."""
        rows = [(self._key(s, target), t) for s, t in pairs.items() if s.strip() and t]
        if not rows:
            return
        with self._lock:
            self._conn.executemany(
                "INSERT OR REPLACE INTO tm (k, translation) VALUES (?, ?)", rows
            )
            self._conn.commit()


class TranslationMemory:
    def __init__(self):
        self.exact: dict[str, str] = {}

    def add(self, source: str, translated: str) -> None:
        s, t = _norm(source), (translated or "").strip()
        if s and t:
            self.exact[s] = t

    def lookup(self, source: str) -> str | None:
        return self.exact.get(_norm(source))

    def dedupe(self, texts: list[str]) -> tuple[list[str], list[int]]:
        """Return (unique_texts, index_map) where index_map[i] points into unique_texts.
        Lets the caller translate only unique strings then scatter results back."""
        seen: dict[str, int] = {}
        unique: list[str] = []
        idx_map: list[int] = []
        for t in texts:
            k = _norm(t)
            if k not in seen:
                seen[k] = len(unique)
                unique.append(t)
            idx_map.append(seen[k])
        return unique, idx_map
