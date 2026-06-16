"""Feedback loop (PR-3): correct -> confirmed TM / authoritative glossary, the corrections audit
trail, review-sidecar import (mechanism 3), edit-reimport alignment (mechanism 2), suggestion
accept, and the tm confirm/stats/purge maintenance."""

from __future__ import annotations

import pytest

from transdoc.store import feedback as fb


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Isolated TM + glossary on a throwaway DB (the session conftest disables persistence)."""
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "f.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.glossary import GlossaryStore
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    GlossaryStore._instance = None
    tm, gs = TMStore.get(), GlossaryStore.get()
    yield tm, gs
    TMStore._instance = None
    GlossaryStore._instance = None


def test_correct_segment_becomes_confirmed_tm(stores):
    tm, _ = stores
    assert fb.record_correction("Hello world", "Halo dunia", "en", "id", scope="segment")
    assert tm.get_many(["Hello world"], "id", src_lang="en") == {"Hello world": "Halo dunia"}
    assert tm.stats()["confirmed"] == 1


def test_correct_term_becomes_authoritative_glossary(stores):
    _, gs = stores
    assert fb.record_correction("Mark", "tanda", "de", "id", scope="term")
    merged, _ = gs.resolve("de", "id")
    assert merged["Mark"] == "tanda"
    assert gs.list("de", "id")[0]["origin"] == "user"      # DeepL-style authoritative tier


def test_correct_term_lock(stores):
    _, gs = stores
    fb.record_correction("Mark", "tanda", "de", "id", scope="term", locked=True)
    _, locked = gs.resolve("de", "id")
    assert "Mark" in locked


def test_correction_audit_row_written(stores):
    tm, _ = stores
    fb.record_correction("x", "y", "en", "id", scope="segment", bad_text="z")
    row = tm._conn.execute("SELECT src_text, corrected, bad_text, scope FROM corrections").fetchone()
    assert row == ("x", "y", "z", "segment")


def test_confirmed_tm_immune_to_engine_overwrite(stores):
    tm, _ = stores
    fb.record_correction("Bank", "bank-fix", "de", "id", scope="segment")
    tm.put_many({"Bank": "engine-val"}, "id", src_lang="de")    # engine result must NOT overwrite
    assert tm.get_many(["Bank"], "id", src_lang="de") == {"Bank": "bank-fix"}


def test_import_review_tsv(stores, tmp_path):
    p = tmp_path / "out.review.tsv"
    fb.write_review([("b1", "Good morning", "Pagi buruk")], p)
    # user fixes the correction column
    text = p.read_text(encoding="utf-8").replace("Pagi buruk\t", "Pagi buruk\tSelamat pagi")
    p.write_text(text, encoding="utf-8")
    n = fb.import_review(p, "en", "id")
    assert n == 1
    tm, _ = stores
    assert tm.get_many(["Good morning"], "id", src_lang="en") == {"Good morning": "Selamat pagi"}


def test_import_review_skips_unfilled_rows(stores, tmp_path):
    p = tmp_path / "out.review.tsv"
    fb.write_review([("b1", "Hello", "Halo")], p)               # correction column left blank
    assert fb.import_review(p, "en", "id") == 0


def test_import_edited_aligns_against_review(stores, tmp_path):
    review = tmp_path / "out.review.tsv"
    fb.write_review([("b1", "One", "Satu"), ("b2", "Two", "Dua")], review)
    edited = tmp_path / "edited.md"
    edited.write_text("Satu\nDUA-FIXED\n", encoding="utf-8")    # second segment edited
    n = fb.import_edited(edited, review, "en", "id")
    assert n == 1
    tm, _ = stores
    assert tm.get_many(["Two"], "id", src_lang="en") == {"Two": "DUA-FIXED"}


def test_import_edited_refuses_on_count_mismatch(stores, tmp_path):
    review = tmp_path / "out.review.tsv"
    fb.write_review([("b1", "One", "Satu"), ("b2", "Two", "Dua")], review)
    edited = tmp_path / "edited.md"
    edited.write_text("only one line\n", encoding="utf-8")      # ambiguous -> import nothing
    assert fb.import_edited(edited, review, "en", "id") == 0


def test_accept_suggestion(stores):
    _, gs = stores
    gs.add_suggestions([("Transdoc", "Transdoc-ID")], "en", "id")
    assert gs.accept_suggestion("Transdoc", "en", "id", locked=True)
    merged, locked = gs.resolve("en", "id")
    assert merged["Transdoc"] == "Transdoc-ID" and "Transdoc" in locked
    assert gs.list_suggestions("en", "id") == []               # dropped from the queue


def test_tm_confirm_and_purge(stores):
    tm, _ = stores
    tm.put_many({"keep": "engine1", "drop": "engine2"}, "id", src_lang="en")
    assert tm.confirm("keep", "id", src_lang="en") == 1
    purged = tm.purge(unconfirmed_only=True)
    assert purged == 1                                          # only the unconfirmed 'drop'
    assert tm.get_many(["keep"], "id", src_lang="en") == {"keep": "engine1"}
