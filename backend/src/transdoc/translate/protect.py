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
    r'(?:\+?\d[\d\s\-().]{7,}\d)',                              # phone numbers
    r'\b\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4}\b',                # numeric dates
    r'\b\d+(?:[.,]\d+)?\s*(?:USD|IDR|MYR|THB|VND|PHP|SGD|EUR|JPY|CNY|kg|km|cm|mm|ml)\b',
    r'[$€£¥₹]\s?\d[\d,]*(?:\.\d+)?',                            # symbol currency $1,299.99 / €50
    r'\b\d+(?:[.,]\d+)?\s?%',                                   # percentages 7.5%, 50 %
    r'\b\d{1,2}:\d{2}(?::\d{2})?\b',                            # clock times 14:05, 08:30:00
    r'#[A-Za-z0-9]+\b',                                         # hash codes / tags #A1B2C3
    r'\$[^$\n]{1,80}\$',                                        # inline LaTeX math $...$
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
    def __init__(self, extra: list[str] | None = None):
        self.extra = [e for e in (extra or []) if e.strip()]

    def _spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
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
            mapping[i] = text[a:b]
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
