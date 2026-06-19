# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Subtitle parse/compose round-trip and IR extraction (timing preserved)."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.extract.subtitle import compose_cues, extract, parse_cues

SRT = """1
00:00:01,000 --> 00:00:04,000
Hello world
second line

2
00:00:05,000 --> 00:00:07,000
Goodbye
"""

VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Hello world
"""


def test_parse_cues_splits_header_and_text():
    cues = parse_cues(SRT)
    assert len(cues) == 2
    assert cues[0]["header"] == ["1", "00:00:01,000 --> 00:00:04,000"]
    assert cues[0]["text"] == ["Hello world", "second line"]


def test_vtt_preamble_is_all_header():
    cues = parse_cues(VTT)
    assert cues[0]["header"] == ["WEBVTT"]
    assert cues[0]["text"] == []
    assert cues[1]["text"] == ["Hello world"]


def test_compose_is_inverse_of_parse():
    cues = parse_cues(SRT)
    assert parse_cues(compose_cues(cues)) == cues


def test_extract_one_block_per_text_cue_with_stable_id(tmp_path):
    f = tmp_path / "s.srt"
    f.write_text(SRT, encoding="utf-8")
    doc = extract(str(f), Config(target_lang="id"))
    assert [b.id for b in doc.blocks] == ["cue0", "cue1"]
    assert doc.blocks[0].text == "Hello world\nsecond line"


def test_extract_skips_empty_cues(tmp_path):
    f = tmp_path / "s.vtt"
    f.write_text(VTT, encoding="utf-8")
    doc = extract(str(f), Config(target_lang="id"))
    # the WEBVTT preamble (no text) must not become a block
    assert [b.id for b in doc.blocks] == ["cue1"]
