# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""GlossaryStore (PR-2): precedence (locked > user > confirmed > auto), domain-then-global,
-g overlay vs locked, suggestion queue, TSV/JSON import-export, and protect→restore-target."""

from __future__ import annotations

import pytest

from transdoc.config import Config
from transdoc.translate.base import _resolve_glossary
from transdoc.translate.protect import Protector


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Isolated glossary store on a throwaway DB. The session-wide conftest sets
    TRANSDOC_TM_DISABLE=1 (kills persistence) — undo it here and point at a temp DB."""
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "g.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.glossary import GlossaryStore
    GlossaryStore._instance = None
    gs = GlossaryStore()
    GlossaryStore._instance = gs
    yield gs
    GlossaryStore._instance = None


def test_add_resolve_roundtrip(store):
    store.add("Transdoc", "Transdoc-ID", "en", "id")
    merged, locked = store.resolve("en", "id")
    assert merged == {"Transdoc": "Transdoc-ID"}
    assert locked == set()


def test_precedence_user_over_confirmed_over_auto(store):
    store.add("Mark", "auto-r", "de", "id", origin="auto")
    store.add("Mark", "confirmed-r", "de", "id", origin="confirmed")
    # last add wins the UNIQUE row, so use distinct terms to prove tier ordering instead:
    store.add("Bank", "auto-bank", "de", "id", origin="auto")
    store.add("Bank", "user-bank", "de", "id", origin="user")   # upsert -> user tier
    merged, _ = store.resolve("de", "id")
    assert merged["Bank"] == "user-bank"
    assert merged["Mark"] == "confirmed-r"


def test_locked_beats_everything_including_g_flag(store):
    store.add("Mark", "tanda-LOCKED", "de", "id", locked=True)
    cfg = Config(source_lang="de", target_lang="id")
    cfg.glossary = {"Mark": "from-g-flag"}                       # -g overlay
    merged, locked = _resolve_glossary(cfg, "de", "id")
    assert "Mark" in locked
    assert merged["Mark"] == "tanda-LOCKED"                      # locked wins over -g


def test_g_flag_overrides_unlocked_db_entry(store):
    store.add("Bank", "db-user", "de", "id", origin="user")     # not locked
    cfg = Config(source_lang="de", target_lang="id")
    cfg.glossary = {"Bank": "from-g"}
    merged, _ = _resolve_glossary(cfg, "de", "id")
    assert merged["Bank"] == "from-g"                           # -g wins over unlocked db user


def test_domain_specific_beats_global_no_cross_domain(store):
    store.add("court", "pengadilan", "en", "id")                # global
    store.add("court", "lapangan", "en", "id", domain="sport")  # sport-specific
    g_global, _ = _resolve_glossary(Config(source_lang="en", target_lang="id", domain="auto"),
                                    "en", "id")
    assert g_global["court"] == "pengadilan"
    g_sport, _ = _resolve_glossary(Config(source_lang="en", target_lang="id", domain="sport"),
                                   "en", "id")
    assert g_sport["court"] == "lapangan"                       # domain entry wins
    g_legal, _ = _resolve_glossary(Config(source_lang="en", target_lang="id", domain="legal"),
                                   "en", "id")
    assert g_legal["court"] == "pengadilan"                     # unknown domain -> global only


def test_remove(store):
    store.add("X", "Y", "en", "id")
    assert store.remove("X", "en", "id") == 1
    assert store.resolve("en", "id")[0] == {}


def test_suggestions_write_and_dedupe(store):
    store.add_suggestions([("Foo", "Bar")], "en", "id")
    store.add_suggestions([("Foo", "Baz")], "en", "id")        # OR IGNORE -> first kept
    sug = store.list_suggestions("en", "id")
    assert len(sug) == 1 and sug[0]["rendering"] == "Bar"
    # suggestions are NOT applied entries
    assert store.resolve("en", "id")[0] == {}


def test_export_import_json_roundtrip(store, tmp_path):
    store.add("Alpha", "AlphaID", "en", "id", domain="tech", locked=True)
    p = tmp_path / "g.json"
    assert store.export(p) == 1
    store.remove("Alpha", "en", "id", domain="tech")
    assert store.import_(p) == 1
    merged, locked = store.resolve("en", "id", "tech")
    assert merged["Alpha"] == "AlphaID" and "Alpha" in locked


def test_export_import_tsv_roundtrip(store, tmp_path):
    store.add("Beta", "BetaID", "de", "id")
    p = tmp_path / "g.tsv"
    store.export(p)
    store.remove("Beta", "de", "id")
    assert store.import_(p) == 1
    assert store.resolve("de", "id")[0]["Beta"] == "BetaID"


def test_protect_restores_target_rendering():
    """The glossary term is masked (engine never sees it) and restored as the TARGET rendering."""
    pr = Protector(extra=["Mark"], renderings={"Mark": "tanda"})
    protected, mapping = pr.protect("Die Mark ist Geld")
    assert "Mark" not in protected and "PH" in protected      # masked before the engine
    assert pr.restore(protected, mapping) == "Die tanda ist Geld"
