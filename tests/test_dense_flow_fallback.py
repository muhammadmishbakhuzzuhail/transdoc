"""Dense-page fallback: if the LAYOUT overlay leaves most blocks illegible, AUTO fidelity
re-renders as FLOW. A few stray illegible blocks keep the overlay."""

from __future__ import annotations

from pathlib import Path

import fitz

from transdoc import pipeline
from transdoc.config import Config, Engine, Fidelity, Mode, OutputFormat


def _plain_pdf(path, n_lines=6):
    d = fitz.open()
    p = d.new_page(width=300, height=400)
    for i in range(n_lines):
        p.insert_text((20, 30 + i * 20), f"Ordinary digital paragraph number {i} here.",
                      fontsize=11)
    d.save(str(path))


def _patch_regen(monkeypatch, illegible_fraction):
    """Replace regenerate with a fake that flags a fraction of blocks illegible on render
    and records how many times it ran + with which fidelity."""
    calls = []

    def fake(doc, cfg, outp):
        calls.append(cfg.fidelity)
        trans = [b for b in doc.blocks if b.is_translatable and b.translated]
        k = int(len(trans) * illegible_fraction)
        for b in trans[:k]:
            b.flags["illegible"] = "x"
        Path(outp).write_text("out")

    monkeypatch.setattr(pipeline, "regenerate", fake)
    return calls


def _run(tmp_path, monkeypatch, fraction):
    src = tmp_path / "d.pdf"
    _plain_pdf(src)
    calls = _patch_regen(monkeypatch, fraction)
    cfg = Config(source_lang="en", target_lang="id", engine=Engine.ECHO,
                 output_format=OutputFormat.PDF, fidelity=Fidelity.AUTO, mode=Mode.FULL)
    pipeline.run(str(src), cfg, out_path=str(tmp_path / "o.pdf"))
    return cfg, calls


def test_mostly_illegible_switches_to_flow(tmp_path, monkeypatch):
    cfg, calls = _run(tmp_path, monkeypatch, fraction=0.9)
    assert cfg.fidelity == Fidelity.FLOW
    assert len(calls) == 2 and calls[1] == Fidelity.FLOW       # re-rendered as flow


def test_few_illegible_keeps_layout(tmp_path, monkeypatch):
    cfg, calls = _run(tmp_path, monkeypatch, fraction=0.15)
    assert cfg.fidelity == Fidelity.AUTO                        # no switch
    assert len(calls) == 1
