# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Rule-based translation QA — deterministic, model-free, always-on.

The memoQ/Xbench-style checks a document translator needs, complementing the optional model-based
COMET-Kiwi QE in quality.py. Each finding carries a severity:

  HARD (almost certainly wrong -> the QE-gate will escalate the segment to the LLM, Area A3):
    - entity     : a number / date / URL / email / code present in the source is missing from the
                   translation (this also catches a dropped [PH] placeholder — its protected token
                   vanishes from the output). The accuracy that matters most for documents.
    - untranslated: the translation came back equal to a substantial source segment.
    - empty      : the source has text but the translation is empty.

  SOFT (advisory flag only):
    - length     : target/source length ratio is outside the band expected for the language pair
                   (possible over/under-translation or hallucination).
    - glossary   : a glossary term's required rendering is absent from the translation.

Findings are attached to ``block.flags`` and summarized in the report's "## QA" section.
See GLOSSARY-TM-FEEDBACK-SPEC.md, Area E.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

HARD_CHECKS = frozenset({"entity", "untranslated", "empty"})
SOFT_CHECKS = frozenset({"length", "glossary"})

# Per-target-language length-ratio band (len(target)/len(source) in characters). Languages that
# pack meaning tightly (CJK/Thai) shrink; agglutinative/compounding ones (de/fi/ru/ar) expand.
# Pairs not listed fall back to the generic band. (translation length-anomaly QA)
_LENGTH_BANDS: dict[str, tuple[float, float]] = {
    "zh": (0.2, 1.1), "ja": (0.2, 1.3), "ko": (0.2, 1.3), "th": (0.3, 1.3),
    "de": (0.7, 2.2), "fi": (0.7, 2.3), "ru": (0.7, 2.2), "ar": (0.6, 2.0),
    "hu": (0.7, 2.2), "nl": (0.8, 2.0),
}
_GENERIC_BAND = (0.5, 2.0)
_MIN_LEN_FOR_RATIO = 25          # don't flag short strings — ratios are noisy there

# Verbatim tokens that must survive translation byte-for-byte. Numbers are normalized to digits-only
# so locale reformatting (1,000 -> 1.000) doesn't false-positive.
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")
_URL = re.compile(r"https?://[^\s<>\"]+|www\.[^\s<>\"]+")
_EMAIL = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


@dataclass
class Finding:
    block_id: str
    check: str
    severity: str        # "hard" | "soft"
    detail: str


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _missing_entities(src: str, tgt: str) -> list[str]:
    """Entities in src absent from tgt. Numbers compared digits-only; urls/emails verbatim."""
    missing: list[str] = []
    tgt_digits = {_digits(m) for m in _NUMBER.findall(tgt)}
    for m in _NUMBER.findall(src):
        d = _digits(m)
        if d and d not in tgt_digits:
            missing.append(m)
    for pat in (_URL, _EMAIL):
        present = set(pat.findall(tgt))
        for m in pat.findall(src):
            if m not in present:
                missing.append(m)
    return missing


def _looks_untranslated(src: str, tgt: str) -> bool:
    if tgt.strip() != src.strip():
        return False
    return len(re.findall(r"[^\W\d_]{4,}", src)) >= 3


def length_band(tgt_lang: str | None) -> tuple[float, float]:
    return _LENGTH_BANDS.get((tgt_lang or "").split("-")[0].lower(), _GENERIC_BAND)


def check_pair(block_id: str, src: str, tgt: str | None, cfg) -> list[Finding]:
    """Run every rule check on one (source, translation) pair."""
    out: list[Finding] = []
    src = src or ""
    if not src.strip():
        return out
    if not (tgt or "").strip():
        out.append(Finding(block_id, "empty", "hard", "translation is empty"))
        return out
    miss = _missing_entities(src, tgt)
    if miss:
        out.append(Finding(block_id, "entity", "hard",
                           "missing in translation: " + ", ".join(miss[:6])))
    if _looks_untranslated(src, tgt):
        out.append(Finding(block_id, "untranslated", "hard", "translation equals source"))
    if len(src) >= _MIN_LEN_FOR_RATIO:
        lo, hi = length_band(cfg.target_lang)
        ratio = len(tgt) / max(1, len(src))
        if ratio < lo or ratio > hi:
            out.append(Finding(block_id, "length", "soft",
                               f"length ratio {ratio:.2f} outside [{lo}, {hi}]"))
    for term, rendering in (cfg.glossary or {}).items():
        if term and rendering and term in src and rendering not in tgt:
            out.append(Finding(block_id, "glossary", "soft",
                               f"glossary '{term}'->'{rendering}' not applied"))
    return out


def run_qa(doc, cfg) -> list[Finding]:
    """Check every translated block + header/footer, attach flags, return all findings."""
    findings: list[Finding] = []
    blocks = [*doc.blocks, *getattr(doc, "headers", []), *getattr(doc, "footers", [])]
    for b in blocks:
        tgt = getattr(b, "translated", None)
        if tgt is None or not b.text.strip():
            continue
        for f in check_pair(b.id, b.text, tgt, cfg):
            findings.append(f)
            b.flags[f"qa_{f.check}"] = f.detail
    return findings


def needs_escalation(findings: list[Finding]) -> bool:
    """QE-gate (Area A3) trigger from rule checks alone: any HARD finding or a length anomaly."""
    return any(f.severity == "hard" or f.check == "length" for f in findings)


def qa_report(findings: list[Finding]) -> str:
    """A '## QA' markdown section summarizing findings, or '' when clean."""
    if not findings:
        return ""
    from collections import Counter
    counts = Counter(f.check for f in findings)
    hard = sum(1 for f in findings if f.severity == "hard")
    lines = [f"- {check}: {n}" for check, n in sorted(counts.items())]
    head = f"\n\n## QA\n{len(findings)} finding(s), {hard} hard:\n" + "\n".join(lines)
    sample = [f for f in findings if f.severity == "hard"][:8]
    if sample:
        head += "\n\nHard findings:\n" + "\n".join(
            f"- `{f.block_id}` {f.check}: {f.detail}" for f in sample)
    return head
