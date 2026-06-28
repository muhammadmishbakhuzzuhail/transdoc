# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
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


def test_tmx_rejects_entity_billion_laughs(stores, tmp_path):
    """A TMX carrying a DTD/internal entity must be rejected, not entity-expanded (XXE/DoS).
    Also padded past the old 4096-byte prefix scan to prove the parser — not a heuristic — blocks it."""
    from transdoc.store.interchange import import_tmx
    tm, _ = stores
    pad = "<!-- " + "x" * 5000 + " -->"
    evil = (
        '<?xml version="1.0"?>\n' + pad + "\n"
        '<!DOCTYPE tmx [ <!ENTITY lol "ha"> <!ENTITY lol2 "&lol;&lol;&lol;"> ]>\n'
        '<tmx version="1.4"><body>'
        '<tu><tuv xml:lang="en"><seg>&lol2;</seg></tuv>'
        '<tuv xml:lang="id"><seg>x</seg></tuv></tu></body></tmx>'
    )
    p = tmp_path / "evil.tmx"
    p.write_text(evil, encoding="utf-8")
    with pytest.raises(ValueError):
        import_tmx(tm, p)


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


def test_glossary_csv_export_neutralises_formula_injection(stores, tmp_path):
    from transdoc.store.interchange import export_glossary_csv
    _, gs = stores
    gs.add("=cmd()", "=HYPERLINK(evil)", "en", "id", origin="user")
    p = tmp_path / "g.csv"
    export_glossary_csv(gs, p)
    text = p.read_text()
    # the formula-sigil cells must be prefixed with ' so a spreadsheet treats them as text
    assert "'=cmd()" in text and "'=HYPERLINK(evil)" in text


def test_glossary_csv_export_neutralises_injection_in_metadata_columns(stores, tmp_path):
    from transdoc.store.interchange import export_glossary_csv
    _, gs = stores
    # a malicious value hidden in the user-supplied domain column (was written raw)
    gs.add("term", "rendering", "en", "id", domain="=cmd()", origin="user")
    p = tmp_path / "g.csv"
    export_glossary_csv(gs, p)
    text = p.read_text()
    assert "'=cmd()" in text                 # domain cell guarded too
    assert "\n=cmd()" not in text and ",=cmd()" not in text


def test_tmx_import_rejects_dtd_entity(stores, tmp_path):
    from transdoc.store.interchange import import_tmx
    tm, _ = stores
    p = tmp_path / "bomb.tmx"
    p.write_text('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]>'
                 "<tmx><body></body></tmx>", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError):
        import_tmx(tm, p)
