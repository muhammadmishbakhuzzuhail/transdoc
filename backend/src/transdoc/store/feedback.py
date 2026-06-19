# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Feedback: turn a human correction into a persisted, reused fix (PR-3).

The correction loop is what makes the system learn — a term the user fixes once (e.g. the 1917
masthead "Mark" → "tanda", a semantic error the rule-based QA cannot catch because the number
survives) is remembered and applied to every later document. Three headless mechanisms feed it:

1. ``record_correction`` — the ``transdoc correct`` CLI. A *segment* fix becomes a confirmed TM
   entry (immune to auto-overwrite); a *term* fix becomes a glossary entry (origin 'user', i.e.
   authoritative — DeepL-style — optionally locked).
2. ``import_review`` — the ``<output>.review.tsv`` sidecar (emitted with ``--review``) has the
   source for every segment; the user fills the ``correction`` column and re-imports. Each filled
   row is a segment correction. (Mechanism 3 in the spec: an editable column.)
3. ``import_edited`` — the user edits the translated output directly; we align it against the same
   review sidecar (which holds source + original translation, in order) and capture changed
   segments. (Mechanism 2 in the spec: edit → re-import.)

Every correction is also appended to the ``corrections`` audit table, so provenance survives even
if the promoted row is later re-corrected or purged.
"""

from __future__ import annotations

import csv
from pathlib import Path

from .glossary import GlossaryStore
from .tm import TMStore

# The columns a review sidecar carries. `correction` is the one the user fills.
REVIEW_COLUMNS = ["block_id", "source", "translation", "correction"]


def _conn():
    """The shared DB connection (via TMStore, which owns one). None when persistence is disabled."""
    tm = TMStore.get()
    return tm._conn if tm is not None else None


def record_correction(source: str, corrected: str, src_lang: str, tgt_lang: str,
                      domain: str = "", scope: str = "segment", bad_text: str | None = None,
                      locked: bool = False) -> bool:
    """Log a correction to the audit table and promote it. ``scope='segment'`` → confirmed TM;
    ``scope='term'`` → glossary (origin 'user', authoritative; ``locked`` raises it above ``-g``).
    Returns False if persistence is disabled or the inputs are empty."""
    if not (source and source.strip() and corrected and corrected.strip() and tgt_lang):
        return False
    domain = "" if domain in ("", "auto") else domain
    conn = _conn()
    if conn is None:
        return False
    conn.execute(
        "INSERT INTO corrections (src_text, src_lang, tgt_lang, domain, bad_text, corrected, scope) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [source, src_lang, tgt_lang, domain, bad_text, corrected, scope],
    )
    conn.commit()
    if scope == "term":
        gs = GlossaryStore.get()
        if gs is not None:
            gs.add(source, corrected, src_lang, tgt_lang, domain=domain, locked=locked, origin="user")
    else:
        tm = TMStore.get()
        if tm is not None:
            tm.put_correction(source, corrected, tgt_lang, src_lang=src_lang, domain=domain)
    return True


def write_review(rows: list[tuple[str, str, str]], path: str | Path) -> int:
    """Write the review sidecar: ``rows`` = [(block_id, source, translation)]; the ``correction``
    column is left blank for the user to fill. Returns the number of segment rows written."""
    p = Path(path)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(REVIEW_COLUMNS)
        for block_id, source, translation in rows:
            w.writerow([block_id, source, translation, ""])
    return len(rows)


def _read_review(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def import_review(path: str | Path, src_lang: str, tgt_lang: str, domain: str = "") -> int:
    """Mechanism 3: read a filled review sidecar; every row whose ``correction`` differs from its
    ``translation`` (and is non-empty) becomes a segment correction. Returns the count imported."""
    n = 0
    for row in _read_review(path):
        source = (row.get("source") or "").strip()
        fix = (row.get("correction") or "").strip()
        old = (row.get("translation") or "").strip()
        if source and fix and fix != old:
            if record_correction(source, fix, src_lang, tgt_lang, domain=domain,
                                  scope="segment", bad_text=old or None):
                n += 1
    return n


def import_edited(edited_path: str | Path, against_path: str | Path,
                  src_lang: str, tgt_lang: str, domain: str = "") -> int:
    """Mechanism 2: the user edited the translated output. Align the edited text against the review
    sidecar's segments (in order, 1:1 by non-empty line/paragraph) and capture the changed ones as
    segment corrections, keyed by the sidecar's source. Returns the count imported.

    Parsing-tolerant: the edited file is split into non-empty trimmed lines; if its line count does
    not match the sidecar's segment count, alignment is ambiguous, so nothing is imported (the user
    should use the review TSV instead). Markdown headings/list markers are compared verbatim."""
    rows = _read_review(against_path)
    if not rows:
        return 0
    text = Path(edited_path).read_text(encoding="utf-8") if Path(edited_path).exists() else ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != len(rows):
        return 0                                    # ambiguous alignment -> refuse (no bad guesses)
    n = 0
    for row, edited in zip(rows, lines):
        source = (row.get("source") or "").strip()
        old = (row.get("translation") or "").strip()
        if source and edited and edited != old:
            if record_correction(source, edited, src_lang, tgt_lang, domain=domain,
                                  scope="segment", bad_text=old or None):
                n += 1
    return n
