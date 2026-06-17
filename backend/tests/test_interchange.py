"""TMX (TM) + CSV (glossary) interchange round-trips."""

from __future__ import annotations

import pytest


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.glossary import GlossaryStore
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    GlossaryStore._instance = None
    yield TMStore.get(), GlossaryStore.get()
    TMStore._instance = None
    GlossaryStore._instance = None


def test_tmx_round_trip(stores, tmp_path):
    from transdoc.store.interchange import export_tmx, import_tmx
    from transdoc.store.tm import TMStore
    tm, _ = stores
    tm.put_correction("Hello world", "Halo dunia", "id", src_lang="en")
    p = tmp_path / "tm.tmx"
    assert export_tmx(tm, p) == 1
    assert "<tmx" in p.read_text() and "Halo dunia" in p.read_text()

    # fresh TM, import the TMX back
    TMStore._instance = None
    import os
    os.environ["TRANSDOC_DB_PATH"] = str(tmp_path / "y.db")
    tm2 = TMStore.get()
    assert import_tmx(tm2, p) == 1
    got = tm2.get_many(["Hello world"], "id", src_lang="en")
    assert got.get("Hello world") == "Halo dunia"


def test_glossary_csv_round_trip(stores, tmp_path):
    from transdoc.store.interchange import export_glossary_csv, import_glossary_csv
    _, gs = stores
    gs.add("API", "API", "en", "id", origin="user")
    gs.add("cloud", "awan", "en", "id", origin="user")
    p = tmp_path / "g.csv"
    assert export_glossary_csv(gs, p) == 2
    text = p.read_text()
    assert "source,target" in text and "awan" in text

    gs.remove("cloud", "en", "id")
    n = import_glossary_csv(gs, p, "en", "id")
    assert n == 2
    entries = {e["term"]: e["rendering"] for e in gs.list("en", "id")}
    assert entries["cloud"] == "awan"


def test_glossary_csv_headerless_with_pair_args(stores, tmp_path):
    from transdoc.store.interchange import import_glossary_csv
    _, gs = stores
    p = tmp_path / "h.csv"
    p.write_text("Mark,tanda\nBank,bank\n", encoding="utf-8")     # no header, DeepL-style
    n = import_glossary_csv(gs, p, "de", "id")
    assert n == 2
    entries = {e["term"]: e["rendering"] for e in gs.list("de", "id")}
    assert entries == {"Mark": "tanda", "Bank": "bank"}
