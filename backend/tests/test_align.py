# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Word-alignment style transfer. The mBERT aligner is heavy, so these tests stub WordAligner.align
with hand-built alignments and check the run-rebuild: styles follow the aligned target words, the
target text is reproduced losslessly, consecutive same-style words merge, and a failed/sparse
alignment falls back to the existing per-run runs."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document, Run, Style
from transdoc.translate import align as align_mod


def _block(translated, runs):
    b = Block(id="b1", type=BlockType.PARAGRAPH, text="".join(r.text for r in runs))
    b.translated = translated
    b.runs = runs
    return b


def _cfg():
    return Config(source_lang="en", target_lang="id", align_styles=True)


def _stub_align(monkeypatch, mapping):
    monkeypatch.setattr(align_mod.WordAligner, "align",
                        lambda self, src, tgt: set(mapping))


def test_style_follows_aligned_word_after_reorder(monkeypatch):
    # source "The red car" with bold on "red"; target reorders to "Mobil merah itu".
    # alignment: The->itu(2), red->merah(1), car->Mobil(0). Bold must land on "merah".
    runs = [Run(text="The ", style=Style()),
            Run(text="red", style=Style(bold=True)),
            Run(text=" car", style=Style())]
    b = _block("Mobil merah itu", runs)
    _stub_align(monkeypatch, {(0, 2), (1, 1), (2, 0)})
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    assert align_mod.restyle_runs(d, _cfg()) == 1
    assert "".join(r.output_text for r in b.runs) == "Mobil merah itu"   # lossless
    bolded = [r.output_text for r in b.runs if r.style.bold]
    assert len(bolded) == 1 and bolded[0].strip() == "merah"   # bold tracks the reordered word


def test_consecutive_same_style_merge(monkeypatch):
    # two plain source words + one bold; target keeps order -> plain words merge into one run.
    runs = [Run(text="the big ", style=Style()),
            Run(text="dog", style=Style(bold=True))]
    b = _block("anjing besar gemuk", runs)   # 3 target words, all aligned to plain except none bold
    _stub_align(monkeypatch, {(0, 0), (1, 1), (1, 2)})   # 'the'->0, 'big'->1,2 ; 'dog' unaligned
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    align_mod.restyle_runs(d, _cfg())
    assert "".join(r.output_text for r in b.runs) == "anjing besar gemuk"
    assert len(b.runs) == 1                                # all plain -> single merged run
    assert not b.runs[0].style.bold


def test_sparse_alignment_falls_back(monkeypatch):
    runs = [Run(text="a ", style=Style()), Run(text="b", style=Style(bold=True))]
    before = list(runs)
    b = _block("satu dua tiga empat", runs)
    _stub_align(monkeypatch, {(0, 0)})           # 1/4 target words < 0.3 coverage -> bail
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    assert align_mod.restyle_runs(d, _cfg()) == 0
    assert b.runs == before                       # unchanged (keep per-run translation)


def test_empty_alignment_falls_back(monkeypatch):
    runs = [Run(text="a ", style=Style()), Run(text="b", style=Style(bold=True))]
    b = _block("satu dua", runs)
    _stub_align(monkeypatch, set())               # model unavailable -> empty
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    assert align_mod.restyle_runs(d, _cfg()) == 0


def test_disabled_by_default(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(align_mod.WordAligner, "align",
                        lambda self, s, t: called.__setitem__("n", called["n"] + 1) or set())
    runs = [Run(text="a ", style=Style()), Run(text="b", style=Style(bold=True))]
    b = _block("satu dua", runs)
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    align_mod.restyle_runs(d, Config(source_lang="en", target_lang="id"))  # align_styles off
    assert called["n"] == 0


def test_single_run_block_untouched(monkeypatch):
    _stub_align(monkeypatch, {(0, 0)})
    b = _block("halo", [Run(text="hello", style=Style(bold=True))])   # only 1 run
    d = Document(source_path="x", mime="text/plain")
    d.blocks = [b]
    assert align_mod.restyle_runs(d, _cfg()) == 0
