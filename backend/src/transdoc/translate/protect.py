# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Token protection (XLIFF-style) + glossary loading.

Before translating, replace things that must survive verbatim — URLs, emails, phone numbers,
dates, currency/units, codes — with neutral placeholders the MT/LLM won't alter, then restore
them afterward. This stops engines from "translating" an email address or mangling an invoice
number. Ported and adapted from the prior project's NER processor.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Order matters: longer / more specific patterns first.
_PATTERNS = [
    r'https?://[^\s<>"]+|www\.[^\s<>"]+',                       # URLs
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',       # emails
    r'\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]{4}){2,}\b',                # IBAN DE89 3704 0044 0532 ...
    r'(?:\+?\d[\d\s\-().]{7,}\d)',                              # phone numbers
    r'\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b',                # numeric dates
    r'\b\d+(?:\.\d+)?[eE][+\-]?\d+\b',                          # scientific notation 1.5e-10
    r'\bv?\d+\.\d+(?:\.\d+)+\b',                                # version / dotted ref v2.0.1, 1.2.3
    r'\b\d+\s?[-–—]\s?\d+\b',                                   # numeric ranges 10-20, 100–200
    r'@[A-Za-z0-9_]{2,}',                                       # @handles / mentions
    r'\b\d+(?:[.,]\d+)?\s*(?:USD|IDR|MYR|THB|VND|PHP|SGD|EUR|JPY|CNY|kg|km|cm|mm|ml)\b',
    r'[$€£¥₹₩₺₴]\s?\d[\d,]*(?:\.\d+)?',                         # symbol currency $1,299.99 / €50 / ₩500
    r'\b\d+(?:[.,]\d+)?\s?%',                                   # percentages 7.5%, 50 %
    r'\b\d{1,2}:\d{2}(?::\d{2})?\b',                            # clock times 14:05, 08:30:00
    r'#[A-Za-z0-9]+\b',                                         # hash codes / tags #A1B2C3
    # inline LaTeX math $...$ — require a real math token (\cmd, sub/super, =, braces) inside so
    # two plain currency amounts ("$5 and $10") aren't swallowed as one span (data-loss audit).
    r'\$(?=[^$\n]*[\\^_={])[^$\n]{1,80}\$',
    r'\\[a-zA-Z]+(?:\{[^{}\n]*\})?',                           # LaTeX commands \alpha, \frac{..}
    r'\b[A-Za-z][A-Za-z0-9]*[_^]\{?[A-Za-z0-9+\-]+\}?',       # sub/superscript var: head_i, W^Q
    r'\b[A-Z]{2,}-?\d{3,}(?:-\d+)?\b',                          # codes like INV-12345
]

# Built-in proper nouns that must stay verbatim. Kept conservative: multi-word or clearly
# unique brand/product/org names (so a single common word like "Apple" isn't masked in
# prose). Matched case-sensitively. Users extend this via the glossary (Protector(extra=...)).
_BRANDS = [
    "Google Brain", "Google Research", "Google Cloud", "Google Translate", "Google Scholar",
    "Google DeepMind", "DeepMind", "OpenAI", "Hugging Face", "Microsoft Research", "Meta AI",
    "Amazon Web Services", "OpenStreetMap", "PyTorch", "TensorFlow", "NVIDIA", "GitHub",
    "GitLab", "LibreOffice", "LibreTranslate", "WhatsApp", "YouTube", "LinkedIn",
]
_BRANDS_RE = re.compile(r"\b(?:" + "|".join(re.escape(b) for b in
                        sorted(_BRANDS, key=len, reverse=True)) + r")\b")

# Placeholder that survives NMT + LLM translation intact (probed against Opus-MT/Marian):
# bracketed ASCII tag with the "PH" prefix is copied verbatim, unlike unicode brackets which
# get stripped/mangled. Restore is also tolerant of a stray leading/trailing space.
_PH = "[PH{}]"                       # e.g. [PH0]
_PH_RE = re.compile(r"\[\s?PH(\d+)\s?\]")


class Protector:
    def __init__(self, extra: list[str] | None = None,
                 renderings: dict[str, str] | None = None):
        """``extra`` = source terms to mask verbatim (the engine never sees them). ``renderings`` maps
        a term to its TARGET rendering: when given, that term's placeholder restores to the rendering
        instead of the source (protect→restore-target glossary application, PR-2). Terms without a
        rendering restore to the source, as before."""
        self.extra = [e for e in (extra or []) if e.strip()]
        self.renderings = {k: v for k, v in (renderings or {}).items() if k and v}

    def _spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        # Literal placeholder-shaped tokens already in the SOURCE (e.g. a doc that mentions "[PH0]"
        # or uses such markers): protect them too, so they get their own index and restore to
        # themselves instead of colliding with the placeholders we assign to real spans.
        for m in _PH_RE.finditer(text):
            spans.append((m.start(), m.end()))
        for pat in _PATTERNS:
            for m in re.finditer(pat, text):
                spans.append((m.start(), m.end()))
        for m in _BRANDS_RE.finditer(text):
            spans.append((m.start(), m.end()))
        for ent in self.extra:
            for m in re.finditer(re.escape(ent), text):
                spans.append((m.start(), m.end()))
        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        merged: list[tuple[int, int]] = []
        cursor = -1
        for a, b in spans:
            if a < cursor:
                continue
            merged.append((a, b))
            cursor = b
        return merged

    def protect(self, text: str) -> tuple[str, dict[int, str]]:
        if not text:
            return text, {}
        spans = self._spans(text)
        if not spans:
            return text, {}
        out, mapping, cursor = [], {}, 0
        for i, (a, b) in enumerate(spans):
            out.append(text[cursor:a])
            out.append(_PH.format(i))
            span = text[a:b]
            # protect→restore-target: a glossary term restores to its TARGET rendering, so the engine
            # never produces (or mistranslates) the term and the pinned rendering is emitted verbatim.
            mapping[i] = self.renderings.get(span, span)
            cursor = b
        out.append(text[cursor:])
        return "".join(out), mapping

    @staticmethod
    def restore(text: str, mapping: dict[int, str]) -> str:
        if not text or not mapping:
            return text

        def repl(m: re.Match) -> str:
            return mapping.get(int(m.group(1)), "")

        return _PH_RE.sub(repl, text)


def load_glossary(path: str | Path | None) -> dict[str, str]:
    """Load a user glossary JSON ({source: target}). Returns {} if missing/invalid."""
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if str(k).strip() and str(v).strip()}
