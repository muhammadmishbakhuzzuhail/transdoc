# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Text direction (RTL / bidi) detection + propagation.

The north-star is "output ≡ input, only the language changes". When the *target* language is
RTL (Arabic, Hebrew, Persian, Urdu, ...), the translated text must render right-to-left even
though the source was LTR — otherwise an EN->AR translation lands flush-left with reversed
punctuation. Extractors fill ``Style.rtl`` for the *source*; this module recomputes it from the
*output* text after translation so every renderer (which already reads ``style.rtl``) does the
right thing.

Two concerns:
  * direction — which way the block/line/cell flows (alignment + ``direction:rtl``).
  * shaping — for raw glyph-draw paths that have no HarfBuzz/UBA shaper (the PyMuPDF
    ``insert_textbox`` fallback), Arabic letters must be reshaped to their presentation forms and
    the logical order flipped to visual order. HTML paths (``insert_htmlbox``, DOCX ``w:bidi``,
    EPUB ``dir``) run the Unicode Bidi Algorithm themselves, so they get *logical* order.
"""

from __future__ import annotations

import re

# RTL target language codes (ISO 639-1/2/3 + a few BCP-47 tags). Used only as a fallback when a
# block carries no strongly-directional characters (e.g. an empty/figure block).
RTL_LANGS = {
    "ar", "ara",          # Arabic
    "he", "heb", "iw",    # Hebrew (iw = legacy code)
    "fa", "fas", "per", "prs",  # Persian / Farsi / Dari
    "ur", "urd",          # Urdu
    "ps", "pus",          # Pashto
    "sd", "snd",          # Sindhi
    "ug", "uig",          # Uyghur
    "yi", "yid",          # Yiddish
    "dv", "div",          # Dhivehi / Maldivian
    "ckb", "ku",          # Kurdish (Sorani)
    "syr",                # Syriac
    "arc",                # Aramaic
    "nqo",                # N'Ko
    "azb",                # South Azerbaijani (Arabic script)
}

# Strongly RTL Unicode ranges: Hebrew, Arabic, Arabic Supplement, Thaana, NKo, Syriac, Arabic
# Extended-A, Arabic Presentation Forms A/B.
_RTL_RE = re.compile(
    "[֐-׿؀-ۿ܀-ݏݐ-ݿހ-޿߀-߿"
    "ࡠ-࡯ࢠ-ࣿיִ-ﭏﭐ-﷿ﹰ-﻿]")
# Strongly LTR scripts that defeat an RTL classification: Latin (+ extensions), Greek, Cyrillic.
_LTR_RE = re.compile("[A-Za-zÀ-ɏͰ-ϿЀ-ӿ]")


def is_rtl_lang(lang: str | None) -> bool:
    """True if a language code is written right-to-left. Accepts BCP-47 tags (ar-EG -> ar)."""
    if not lang:
        return False
    base = re.split(r"[-_]", lang.strip().lower(), maxsplit=1)[0]
    return base in RTL_LANGS


def rtl_ratio(text: str) -> float:
    """Fraction of strongly-directional characters that are RTL (0..1). 0 when no directional
    characters are present (digits/punctuation/whitespace are neutral and don't count)."""
    rtl = len(_RTL_RE.findall(text or ""))
    ltr = len(_LTR_RE.findall(text or ""))
    total = rtl + ltr
    return rtl / total if total else 0.0


def is_rtl_text(text: str, threshold: float = 0.4) -> bool:
    """True when RTL characters dominate the directional content of ``text``."""
    return rtl_ratio(text) >= threshold


def is_mixed_bidi(text: str) -> bool:
    """True when one string mixes RTL and strong-LTR runs (Arabic prose with a Latin acronym/URL).
    These are the lines a naive shaper misorders, so callers flag them for review."""
    text = text or ""
    return bool(_RTL_RE.search(text) and _LTR_RE.search(text))


def effective_rtl(text: str, target_lang: str | None = None) -> bool:
    """Direction a renderer should use for ``text``: decided by the text's own characters when it
    has any directional content, else by the target language. So a Latin URL stays LTR even in an
    Arabic document, while an empty/figure block inherits the document's target direction."""
    if text and (_RTL_RE.search(text) or _LTR_RE.search(text)):
        return is_rtl_text(text)
    return is_rtl_lang(target_lang)


def shape_for_raw_draw(text: str, rtl: bool) -> str:
    """Reshape + reorder ``text`` for a glyph-draw path with NO bidi/shaping engine (PyMuPDF
    ``insert_textbox``). Joins Arabic letters into presentation forms and flips logical->visual
    order via the Unicode Bidi Algorithm. Returns ``text`` unchanged when not RTL or when the
    optional libs (arabic-reshaper / python-bidi) aren't installed."""
    if not rtl or not text:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except Exception:
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def apply_text_direction(doc, cfg) -> None:
    """Post-translate pass: recompute ``Style.rtl`` from the *output* text (and target language)
    for every block, inline run, and table cell, so the renderers flow translated RTL text the
    right way. Idempotent; safe to skip-call (no-op when nothing is RTL)."""
    target = getattr(cfg, "target_lang", None)
    for b in doc.blocks:
        b.style.rtl = effective_rtl(b.output_text, target)
        for r in b.runs:
            r.style.rtl = effective_rtl(r.output_text, target)
        if b.table is not None:
            _table_direction(b.table, target)


def _table_direction(table, target: str | None) -> None:
    for row in table.rows:
        for cell in row:
            # Cell has no rtl field; right-align RTL cells (unless an explicit align was extracted).
            if not cell.align and effective_rtl(cell.output_text, target):
                cell.align = "right"
            if cell.table is not None:
                _table_direction(cell.table, target)
