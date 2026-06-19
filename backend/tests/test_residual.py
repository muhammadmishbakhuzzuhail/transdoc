# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Residual foreign-script cleanup: non-Latin runs the engine left in a Latin-target output get
re-translated; runs of different scripts are handled separately; non-Latin targets are skipped."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Document
from transdoc.translate.residual import retranslate_foreign_runs, _FOREIGN


class _Stub:
    cacheable = True
    _MAP = {"中文文本。": "teks Cina", "العربية": "Arab", "世界": "dunia"}

    def translate_batch(self, texts, cfg, src=None):
        return [self._MAP.get(t.strip(), t) for t in texts]


def _doc(translated):
    d = Document(source_path="x", mime="docx")
    b = Block(id="1", type=BlockType.PARAGRAPH, text="x")
    b.translated = translated
    d.blocks = [b]
    return d, b


def test_splits_runs_by_script():
    # different scripts separated by a space must be separate runs (so each is detected on its own)
    assert _FOREIGN.findall("a 中文文本。 العربية b") == ["中文文本。", "العربية"]


def test_retranslates_leftover_foreign_runs():
    d, b = _doc("Bahasa inggris. 中文文本。 العربية. Terima kasih")
    n = retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="id"))
    assert n == 1
    assert "teks Cina" in b.translated and "Arab" in b.translated
    assert "中文" not in b.translated and "العربية" not in b.translated


def test_skips_non_latin_target():
    # target is Chinese -> foreign script is expected, don't touch it
    d, b = _doc("世界 hello")
    assert retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="zh")) == 0
    assert b.translated == "世界 hello"


def test_noop_when_no_foreign():
    d, b = _doc("Teks Indonesia biasa saja.")
    assert retranslate_foreign_runs(d, _Stub(), Config(source_lang="en", target_lang="id")) == 0
