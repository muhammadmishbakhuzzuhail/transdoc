"""End-to-end pipeline on a text file with the offline echo engine (no network)."""

from __future__ import annotations

from transdoc.config import Config, Engine, Mode, OutputFormat
from transdoc.pipeline import run


def test_text_to_markdown_end_to_end(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("Hello world.\n\nSecond paragraph.\n", encoding="utf-8")
    out = tmp_path / "out.md"
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO,
                               output_format=OutputFormat.MARKDOWN), str(out))
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "[id] Hello world." in text
    # a report is written next to the output
    assert res.report_path and res.report_path.endswith(".report.md")


def test_diagnose_only_produces_no_output(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("Just diagnosing.\n", encoding="utf-8")
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO, mode=Mode.DIAGNOSE))
    assert res.output_path is None
    assert res.report_text


def test_run_records_per_stage_timings(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("Hello world.\n\nSecond paragraph.\n", encoding="utf-8")
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO,
                               output_format=OutputFormat.MARKDOWN), str(tmp_path / "o.md"))
    # observability: each pipeline stage is timed and surfaced in the report
    assert {"detect", "extract", "translate", "regenerate"} <= set(res.timings)
    assert all(v >= 0 for v in res.timings.values())
    assert "## Timing" in res.report_text


def test_diagnose_mode_also_timed(tmp_path):
    src = tmp_path / "in.txt"
    src.write_text("Hello world.\n", encoding="utf-8")
    res = run(str(src), Config(target_lang="id", engine=Engine.ECHO, mode=Mode.DIAGNOSE))
    assert "detect" in res.timings and "extract" in res.timings
    assert "## Timing" in res.report_text
