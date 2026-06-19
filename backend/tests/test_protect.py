# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Token protection: placeholders must round-trip and survive a translation pass."""

from __future__ import annotations

from transdoc.translate.protect import Protector, load_glossary


def test_protect_restore_roundtrip():
    p = Protector()
    text = "Email me at john.doe@example.com or visit https://example.org/page now."
    protected, mapping = p.protect(text)
    # the verbatim tokens are replaced by placeholders, not present in the protected text
    assert "john.doe@example.com" not in protected
    assert "https://example.org/page" not in protected
    assert "[PH0]" in protected and "[PH1]" in protected
    assert Protector.restore(protected, mapping) == text


def test_placeholder_survives_simulated_translation():
    # An engine that uppercases words but leaves bracketed ASCII tags intact (Google/MT do).
    p = Protector()
    protected, mapping = p.protect("Invoice INV-12345 total 200 USD due today")
    translated = protected.upper()  # stand-in for a real engine mangling words
    restored = Protector.restore(translated, mapping)
    assert "INV-12345" in restored
    assert "200 USD" in restored


def test_restore_tolerates_spaced_placeholder():
    # Some engines insert a space inside the tag: "[PH 0]" / "[ PH0 ]". Restore must cope.
    mapping = {0: "a@b.com"}
    assert Protector.restore("write [ PH0 ] please", mapping) == "write a@b.com please"


def test_no_tokens_is_identity():
    p = Protector()
    out, mapping = p.protect("just some plain words")
    assert out == "just some plain words"
    assert mapping == {}


def test_extra_entities_protected():
    p = Protector(extra=["ACME Corp"])
    protected, mapping = p.protect("Welcome to ACME Corp headquarters")
    assert "ACME Corp" not in protected
    assert Protector.restore(protected, mapping) == "Welcome to ACME Corp headquarters"


def test_inline_math_protected():
    p = Protector()
    text = "The head_i = Attention(W^Q) and $x_{ij}$ values"
    protected, mapping = p.protect(text)
    assert "head_i" not in protected and "W^Q" not in protected and "$x_{ij}$" not in protected
    assert Protector.restore(protected, mapping) == text


def test_plain_prose_not_over_protected():
    p = Protector()
    out, mapping = p.protect("the cat sat on the mat today")
    assert mapping == {}


def test_brand_names_protected_case_sensitively():
    p = Protector()
    protected, mapping = p.protect("Ashish at Google Brain used PyTorch and OpenAI tools")
    assert "Google Brain" not in protected   # multi-word brand kept verbatim
    assert "PyTorch" not in protected
    assert Protector.restore(protected, mapping) == "Ashish at Google Brain used PyTorch and OpenAI tools"
    # lowercase common words must NOT be masked
    out, m = p.protect("an apple and the brain are common words")
    assert m == {}


def test_money_percent_time_hashcode_protected():
    """Preservation-eval finding: prices, percentages, clock times, and #codes were reformatted
    by the engine because they weren't protected. They must now round-trip verbatim."""
    p = Protector()
    text = "Pay $1,299.99 (7.5% tax) for order #A1B2C3 at 14:05."
    protected, mapping = p.protect(text)
    for tok in ("$1,299.99", "7.5%", "#A1B2C3", "14:05"):
        assert tok not in protected, f"{tok} not protected"
    # survives an engine that uppercases/reformats words but keeps [PHn] tags
    assert Protector.restore(protected.upper(), mapping).upper() == text.upper()
    assert Protector.restore(protected, mapping) == text


def test_extended_entity_patterns_protected():
    """Audit additions: versions, numeric ranges, scientific notation, @handles, IBANs, and more
    currency symbols must round-trip verbatim; plain prose must not be touched."""
    p = Protector()
    cases = {
        "Use v2.0.1 here": ["v2.0.1"],
        "range 10-20 today": ["10-20"],
        "value 1.5e-10 ok": ["1.5e-10"],
        "ping @alice now": ["@alice"],
        "pay ₩500 and ₺75": ["₩500", "₺75"],
    }
    for text, toks in cases.items():
        protected, mapping = p.protect(text)
        for tok in toks:
            assert tok not in protected, f"{tok} not protected in {text!r}"
        assert Protector.restore(protected, mapping) == text
    # prose with bare decimals/words must NOT be over-protected
    out, m = p.protect("the rate fell by half over the year")
    assert m == {}


def test_two_currency_amounts_not_swallowed_by_latex():
    """Audit data-loss bug: the inline-LaTeX $...$ pattern used to span from the first $ to the
    second, masking the text between two prices. Both amounts must protect independently and the
    connective text must survive."""
    p = Protector()
    text = "Pay $5 and $10 now"
    protected, mapping = p.protect(text)
    assert "$5" not in protected and "$10" not in protected
    assert "and" in protected and "now" in protected   # middle text not eaten
    assert len(mapping) == 2
    assert Protector.restore(protected, mapping) == text
    # real inline math still protected
    m_protected, m_map = p.protect(r"The $x_{ij}$ and $\alpha$ values")
    assert "$x_{ij}$" not in m_protected and r"$\alpha$" not in m_protected


def test_iso_code_not_broken_by_time_pattern():
    """The clock-time pattern must not chop 'ISO 9001:2015' (4-digit:4-digit is not a time)."""
    p = Protector()
    protected, mapping = p.protect("See ISO 9001:2015 for details.")
    assert Protector.restore(protected, mapping) == "See ISO 9001:2015 for details."


def test_load_glossary_missing_returns_empty(tmp_path):
    assert load_glossary(None) == {}
    assert load_glossary(tmp_path / "nope.json") == {}


def test_load_glossary_reads_pairs(tmp_path):
    g = tmp_path / "g.json"
    g.write_text('{"cat": "kucing", "  ": "skip", "dog": ""}', encoding="utf-8")
    assert load_glossary(g) == {"cat": "kucing"}


def test_literal_placeholder_in_source_does_not_collide():
    # a source that literally contains "[PH0]" must not corrupt a real protected span (regression:
    # the literal token + an assigned placeholder both became [PH0], so restore duplicated the email)
    p = Protector()
    text = "literal [PH0] bracket then a@b.com"
    protected, mapping = p.protect(text)
    assert Protector.restore(protected, mapping) == text


def test_multiple_literal_placeholders_roundtrip():
    p = Protector()
    text = "[PH3] and [PH7] markers with https://a.com link"
    protected, mapping = p.protect(text)
    assert Protector.restore(protected, mapping) == text
