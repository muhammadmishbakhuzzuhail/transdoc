# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""FLORES chrF eval — non-network parts (lang map, FLORES_DIR override, line reader, arg
validation). The translation loop needs network + an online engine and is not exercised here."""

from __future__ import annotations

from scripts import eval_translate


def test_lang_map_covers_scripts():
    # a spread of script families must be present so a per-script regression is visible
    codes = set(eval_translate.LANGS.values())
    assert {"fra_Latn", "rus_Cyrl", "ell_Grek", "arb_Arab", "hin_Deva",
            "zho_Hans", "jpn_Jpan", "tha_Thai"} <= codes
    assert eval_translate._SRC_FLORES == "eng_Latn"


def test_flores_dir_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FLORES_DIR", str(tmp_path))
    assert eval_translate.flores_dir() == tmp_path


def test_lines_reads_first_n(tmp_path):
    p = tmp_path / "x.dev"
    p.write_text("\n".join(f"line {i}" for i in range(10)), encoding="utf-8")
    assert eval_translate._lines(p, 3) == ["line 0", "line 1", "line 2"]


def test_unknown_lang_exits_before_network():
    # bad lang code is rejected (rc 2) before any FLORES download / translation call
    assert eval_translate.main(["zz"]) == 2
