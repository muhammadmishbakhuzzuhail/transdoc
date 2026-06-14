"""Eval harness: run the pipeline over a tiny corpus (echo engine, deterministic) and gate a
regression against a saved baseline."""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz")

from transdoc.config import Config, Engine, OutputFormat  # noqa: E402
from transdoc.eval.harness import diff_baseline, run_corpus  # noqa: E402


def _corpus(tmp_path):
    d = fitz.open()
    p = d.new_page(width=595, height=842)
    p.insert_text((42, 60), "A heading line", fontsize=16)
    p.insert_text((42, 100), "Some body text to translate on this page.", fontsize=11)
    d.save(str(tmp_path / "doc.pdf"))
    d.close()
    return tmp_path


def test_run_corpus_scores_each_doc(tmp_path):
    corpus = _corpus(tmp_path)
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.PDF)
    card = run_corpus(corpus, cfg)
    assert card["engine"] == "echo"
    row = card["docs"]["doc.pdf"]
    assert "error" not in row
    assert row["blocks"] >= 1
    assert row["reading_order_monotonic"] is True
    # output PDF was rendered, so rendering-fidelity counts are present
    assert "overwrite" in row and "tiny" in row and "overflow" in row


def test_baseline_diff_flags_regression():
    base = {"docs": {"a.pdf": {"blocks": 10, "formulas": 4, "flagged": 1,
                               "reading_order_monotonic": True, "chrf": 80.0}}}
    # current: formulas dropped, flagged grew, order broke, chrf cratered
    cur = {"docs": {"a.pdf": {"blocks": 10, "formulas": 1, "flagged": 5,
                              "reading_order_monotonic": False, "chrf": 60.0}}}
    regress = diff_baseline(base, cur)
    joined = " | ".join(regress)
    assert "formulas 4 -> 1" in joined
    assert "flagged 1 -> 5" in joined
    assert "monotonic" in joined
    assert "chrf" in joined


def test_baseline_diff_clean_when_stable():
    base = {"docs": {"a.pdf": {"blocks": 10, "formulas": 4, "flagged": 1,
                               "reading_order_monotonic": True}}}
    # improvement (more formulas, fewer flags) is not a regression
    cur = {"docs": {"a.pdf": {"blocks": 12, "formulas": 5, "flagged": 0,
                              "reading_order_monotonic": True}}}
    assert diff_baseline(base, cur) == []


def test_sidecar_files_are_not_scored_as_documents(tmp_path):
    """gold/ref/out sidecars share the .txt extension but must not be scored as documents."""
    corpus = _corpus(tmp_path)
    (corpus / "doc.gold.txt").write_text("ground truth", encoding="utf-8")
    (corpus / "doc.ref.id.txt").write_text("terjemahan acuan", encoding="utf-8")
    cfg = Config(target_lang="id", engine=Engine.ECHO, output_format=OutputFormat.PDF)
    card = run_corpus(corpus, cfg)
    assert set(card["docs"]) == {"doc.pdf"}   # only the real document, no sidecars


def test_baseline_diff_flags_missing_and_new_error():
    base = {"docs": {"gone.pdf": {"blocks": 3}, "ok.pdf": {"blocks": 3}}}
    cur = {"docs": {"ok.pdf": {"error": "ValueError: boom", "blocks": 3}}}
    regress = diff_baseline(base, cur)
    joined = " | ".join(regress)
    assert "gone.pdf: missing" in joined
    assert "ok.pdf: now errors" in joined
