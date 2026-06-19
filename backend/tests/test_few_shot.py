# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Feedback flywheel (PR): the user's most similar CONFIRMED corrections are injected as few-shot
examples into the LLM prompt. No model call — exercises retrieval + prompt assembly."""

from __future__ import annotations

import pytest


@pytest.fixture
def tm(tmp_path, monkeypatch):
    monkeypatch.delenv("TRANSDOC_TM_DISABLE", raising=False)
    monkeypatch.setenv("TRANSDOC_DB_PATH", str(tmp_path / "x.db"))
    monkeypatch.setenv("TRANSDOC_TM_PATH", str(tmp_path / "legacy.sqlite"))
    from transdoc.store.tm import TMStore
    TMStore._instance = None
    store = TMStore.get()
    yield store
    TMStore._instance = None


def _cfg():
    from transdoc.config import Config
    c = Config(source_lang="en", target_lang="id")
    c.embed_model = None        # force lexical similarity (no sentence-transformers in CI)
    c.domain = ""
    return c


def test_few_shot_retrieves_confirmed_correction(tm):
    from transdoc.translate.ollama import OllamaTranslator
    tm.put_correction("Hello world", "Halo dunia", "id", src_lang="en")     # confirmed=1
    ex = OllamaTranslator()._few_shot(_cfg(), "en", ["Hello world!"])
    assert ("Hello world", "Halo dunia") in ex


def test_unconfirmed_engine_rows_excluded(tm):
    from transdoc.translate.ollama import OllamaTranslator
    tm.put_many({"Hello world": "engine-output"}, "id", src_lang="en")      # confirmed=0
    ex = OllamaTranslator()._few_shot(_cfg(), "en", ["Hello world!"])
    assert ex == []                                                          # engine TM not used


def test_examples_injected_into_system_prompt(tm):
    from transdoc.translate.ollama import OllamaTranslator
    sys = OllamaTranslator()._system(_cfg(), "en", [("Hello world", "Halo dunia")])
    assert "Halo dunia" in sys and "this user" in sys.lower()


def test_disabled_flag_returns_no_examples(tm):
    from transdoc.translate.ollama import OllamaTranslator
    tm.put_correction("Hello world", "Halo dunia", "id", src_lang="en")
    cfg = _cfg()
    cfg.few_shot = False
    assert OllamaTranslator()._few_shot(cfg, "en", ["Hello world!"]) == []
