# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Rule-based translation QA: per-check detection, severity, escalation signal, report."""

from __future__ import annotations

from transdoc.config import Config
from transdoc.ir import Block, BlockType, Confidence, Document
from transdoc.translate.qa import check_pair, needs_escalation, qa_report, run_qa


def _cfg(**kw):
    return Config(target_lang=kw.pop("target_lang", "id"), **kw)


def test_entity_mismatch_detects_dropped_number():
    f = check_pair("b", "Pay 1500 now", "Bayar sekarang", _cfg())
    assert any(x.check == "entity" and x.severity == "hard" for x in f)


def test_entity_ok_when_number_survives_with_locale_reformat():
    # 1,500 -> 1.500 keeps the digits -> not flagged
    assert check_pair("b", "Pay 1,500 now", "Bayar 1.500 sekarang", _cfg()) == []


def test_url_and_email_must_survive():
    f = check_pair("b", "Mail a@b.com via https://x.io", "Kirim surat", _cfg())
    kinds = {x.check for x in f}
    assert "entity" in kinds


def test_untranslated_is_hard():
    f = check_pair("b", "This is a long enough sentence", "This is a long enough sentence", _cfg())
    assert any(x.check == "untranslated" and x.severity == "hard" for x in f)


def test_empty_translation_is_hard():
    f = check_pair("b", "Some real source text here", "   ", _cfg())
    assert any(x.check == "empty" and x.severity == "hard" for x in f)


def test_length_anomaly_is_soft():
    src = "A reasonably long source sentence that should translate to similar length."
    f = check_pair("b", src, "x.", _cfg())               # absurdly short target
    assert any(x.check == "length" and x.severity == "soft" for x in f)


def test_cjk_target_does_not_falsely_flag_shrink():
    src = "A reasonably long source sentence that should translate to similar length."
    # a realistic Chinese rendering is far shorter than the English (denser script) — ~0.3 ratio
    f = check_pair("b", src, "一个相当长的源句子，应翻译成相似的长度内容。", _cfg(target_lang="zh"))
    assert not any(x.check == "length" for x in f)        # CJK band allows the shrink


def test_glossary_adherence_soft():
    cfg = _cfg(glossary={"Transformer": "Transformator"})
    f = check_pair("b", "The Transformer model", "Model Transformer", cfg)   # rendering not applied
    assert any(x.check == "glossary" and x.severity == "soft" for x in f)


def test_needs_escalation_on_hard_or_length():
    from transdoc.translate.qa import Finding
    assert needs_escalation([Finding("b", "entity", "hard", "")])
    assert needs_escalation([Finding("b", "length", "soft", "")])
    assert not needs_escalation([Finding("b", "glossary", "soft", "")])


def test_run_qa_flags_blocks_and_reports():
    doc = Document(source_path="x.txt", mime="text/plain")
    blk = Block(id="b0", type=BlockType.PARAGRAPH, page=0, text="Pay 42 dollars",
                confidence=Confidence(source="digital"))
    blk.translated = "Bayar dolar"          # 42 dropped
    doc.blocks = [blk]
    findings = run_qa(doc, _cfg())
    assert findings and "qa_entity" in blk.flags
    assert "## QA" in qa_report(findings)
    assert qa_report([]) == ""
