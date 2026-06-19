# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""The persistent TM must not be poisoned by a no-op engine: echo marks itself
non-cacheable, so its '[id] ...' placeholders are never written to the cross-run cache."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate import base
from transdoc.translate import memory as tm_mod
from transdoc.translate.echo import EchoTranslator


class _RecordingTM:
    def __init__(self):
        self.put_calls = 0

    def get_many(self, sources, target):
        return {}

    def put_many(self, pairs, target):
        self.put_calls += 1


class _RealEngine:
    name = "real"                      # no cacheable attr -> defaults to cacheable

    def translate_batch(self, texts, cfg, src=None):
        return [f"<<{t}>>" for t in texts]


def _run(tr, monkeypatch):
    tm = _RecordingTM()
    monkeypatch.setattr(tm_mod.PersistentTM, "get", classmethod(lambda cls: tm))
    doc = Document(source_path="x.txt", mime="text/plain")
    doc.blocks = [Block(id="b", type=BlockType.PARAGRAPH, page=0,
                        text="Hello world this is real text.",
                        confidence=Confidence(source="digital"))]
    base.translate_document(doc, tr, Config(target_lang="id"))
    return tm.put_calls


def test_echo_does_not_write_tm(monkeypatch):
    assert EchoTranslator.cacheable is False
    assert _run(EchoTranslator(), monkeypatch) == 0


def test_real_engine_writes_tm(monkeypatch):
    assert _run(_RealEngine(), monkeypatch) == 1
