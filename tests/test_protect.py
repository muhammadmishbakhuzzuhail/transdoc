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


def test_load_glossary_missing_returns_empty(tmp_path):
    assert load_glossary(None) == {}
    assert load_glossary(tmp_path / "nope.json") == {}


def test_load_glossary_reads_pairs(tmp_path):
    g = tmp_path / "g.json"
    g.write_text('{"cat": "kucing", "  ": "skip", "dog": ""}', encoding="utf-8")
    assert load_glossary(g) == {"cat": "kucing"}
