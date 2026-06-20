# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Language detection: lingua backend (opt-in) with langdetect fallback."""

from __future__ import annotations

import pytest

from transdoc import diagnose
from transdoc.diagnose import _lingua_detect, detect_lang


@pytest.fixture(autouse=True)
def _reset_lingua_cache():
    diagnose._LINGUA = {"tried": False, "detector": None}
    yield
    diagnose._LINGUA = {"tried": False, "detector": None}


def test_detect_lang_english_either_backend():
    # works regardless of which backend is installed
    assert detect_lang("This is a clearly English sentence about cats and dogs.") == "en"


def test_disable_lingua_env_forces_fallback(monkeypatch):
    monkeypatch.setenv("TRANSDOC_DISABLE_LINGUA", "1")
    assert _lingua_detect("This is an English sentence.") is None
    # detect_lang still works via langdetect
    assert detect_lang("This is a clearly English sentence about cats and dogs.") == "en"


def test_lingua_detects_iso_code():
    pytest.importorskip("lingua")
    # lingua fixes langdetect's Chinese-as-Korean full-text miss
    assert _lingua_detect("This is a longer English passage with several words.") == "en"
    assert _lingua_detect("Это предложение написано на русском языке полностью.") == "ru"


def test_explicit_source_sets_doc_source_lang(tmp_path):
    # regression: an explicit --source set profile.source_langs but never doc.source_lang, which
    # downstream glossary/engine-src/German-guard/TM all read -> glossary silently disabled.
    from pathlib import Path

    from transdoc.config import Config
    from transdoc.diagnose import diagnose
    from transdoc.ingest.detect import Detection, Kind
    from transdoc.ir import Block, BlockType, Document
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="1", type=BlockType.PARAGRAPH, text="Bonjour le monde, ceci est un test.")]
    det = Detection(kind=Kind.TEXT, mime="text/plain", path=Path("x.txt"), notes=[])
    diagnose(doc, det, Config(source_lang="fr", target_lang="id"))
    assert doc.source_lang == "fr"
