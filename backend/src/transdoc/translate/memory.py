# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Translation memory — exact-match reuse for consistency + fewer engine calls.

Identical source segments translate once and reuse everywhere (a document repeats headers,
labels, table cells). This both enforces consistency and cuts cost/latency.

Two layers:
- ``TranslationMemory``  : in-memory, per-run dedupe (cuts repeats within one document).
- ``PersistentTM``       : the cross-run SQLite cache, now backed by ``store.tm.TMStore`` over the
  unified database (see GLOSSARY-TM-FEEDBACK-SPEC.md). Re-exported here under the old name so
  callers/tests are unchanged. This is what keeps a free Google-web-endpoint service under the rate
  limit — a segment translated once is never sent to Google again.
"""

from __future__ import annotations

from ..store.tm import TMStore as PersistentTM  # noqa: F401  (back-compat re-export)
from ..store.tm import _norm


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
