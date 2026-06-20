# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Document-level consistency: identical source -> one translation (confirmed > majority > first)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document


def _b(bid, text, translated):
    b = Block(id=bid, type=BlockType.PARAGRAPH, text=text)
    b.translated = translated
    return b


def _cfg():
    return Config(source_lang="en", target_lang="id")


def test_majority_wins_and_flags_changes(monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")          # no TM -> majority path
    from transdoc.translate.consistency import enforce_consistency
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Total amount", "Jumlah total"),
                _b("b", "Total amount", "Total jumlah"),
                _b("c", "Total amount", "Jumlah total")]    # majority = "Jumlah total"
    n = enforce_consistency(d, _cfg())
    assert n == 1                                            # only block b changed
    assert all(b.translated == "Jumlah total" for b in d.blocks)
    assert "consistency_normalized" in d.blocks[1].flags
    assert "consistency_normalized" not in d.blocks[0].flags


def test_normalized_match_groups_case_and_space(monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    from transdoc.translate.consistency import enforce_consistency
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Sign here", "Tanda tangan di sini"),
                _b("b", "sign  here ", "Bertanda tangan")]   # same source after normalisation
    enforce_consistency(d, _cfg())
    assert d.blocks[0].translated == d.blocks[1].translated


def test_no_change_when_already_consistent(monkeypatch):
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    from transdoc.translate.consistency import enforce_consistency
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Hello", "Halo"), _b("b", "Hello", "Halo")]
    assert enforce_consistency(d, _cfg()) == 0


def test_harmonised_styled_block_collapses_runs(monkeypatch):
    # a styled (multi-run) block: renderers prefer runs over .translated, so consistency must also
    # collapse the runs onto run 0 — else the harmonised text is silently discarded at render.
    monkeypatch.setenv("TRANSDOC_TM_DISABLE", "1")
    from transdoc.ir import Run
    from transdoc.translate.consistency import enforce_consistency
    losing = Block(id="b", type=BlockType.PARAGRAPH, text="Total amount")
    losing.translated = "Total jumlah"
    losing.runs = [Run(text="Total ", translated="Total "), Run(text="amount", translated="jumlah")]
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Total amount", "Jumlah total"),
                _b("c", "Total amount", "Jumlah total"), losing]   # majority = "Jumlah total"
    enforce_consistency(d, _cfg())
    assert losing.translated == "Jumlah total"
    assert losing.runs[0].output_text == "Jumlah total"            # winner carried by run 0
    assert losing.runs[1].output_text == ""                        # other runs blanked


def test_confirmed_correction_wins_over_majority(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    tm = TMStore.get()
    tm.put_correction("Total amount", "Nilai total", "id", src_lang="en")   # confirmed
    from transdoc.translate.consistency import enforce_consistency
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [_b("a", "Total amount", "Jumlah total"),
                _b("b", "Total amount", "Jumlah total"),
                _b("c", "Total amount", "Total jumlah")]    # differ -> majority "Jumlah total"
    enforce_consistency(d, _cfg())
    assert all(b.translated == "Nilai total" for b in d.blocks)   # confirmed beats majority
    TMStore._instance = None
