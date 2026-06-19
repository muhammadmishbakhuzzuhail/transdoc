"""Residual foreign-script cleanup: re-translate non-Latin runs the engine left behind.

A segment declared as one source language but containing inline OTHER scripts (e.g. an English doc
with "... 中文文本。 العربية ...") comes back with only the source-language parts translated — the
engine leaves the foreign-script spans verbatim. For a Latin-script target that violates "output is
all in the target language". This pass finds the leftover non-Latin runs in the translated text and
re-translates each with auto source detection.

Latin-script targets only: when the TARGET itself is non-Latin (zh/ja/ar/...), foreign-script text
in the output is expected, so the pass is skipped.
"""

from __future__ import annotations

import re

from ..config import Config

# Letters of the major non-Latin scripts: Greek, Cyrillic, Hebrew, Arabic, Devanagari, Bengali,
# Tamil, Telugu, Malayalam, Thai, Hangul, Kana, CJK. A "run" is foreign letters + CJK punctuation
# only — NO ASCII space, so different scripts separated by a space (e.g. "中文。 العربية") split into
# separate runs and each is auto-detected + translated on its own (joining them would let the engine
# detect only the dominant script and leave the other verbatim).
_L = (r"Ͱ-ϿЀ-ԯ֐-׿؀-ۿݐ-ݿ"
      r"ऀ-ॿঀ-৿஀-௿ఀ-౿ഀ-ൿ"
      r"฀-๿ᄀ-ᇿ぀-ヿ㄰-㆏㐀-䶿一-鿿가-힯")
_FOREIGN = re.compile(rf"[{_L}][{_L}　。、，！？：；]*")

# Targets whose own script is non-Latin — skip the pass for these (foreign script is the point).
_NON_LATIN_TARGETS = {
    "zh", "ja", "ko", "ar", "fa", "ur", "he", "hi", "mr", "ne", "bn", "ta", "te", "kn", "ml",
    "th", "ru", "uk", "bg", "sr", "el",
}


def _fields(doc):
    """All translated text holders (block, run, table cell) as (obj, current_text)."""
    out = []
    for b in doc.blocks:
        if getattr(b, "translated", None):
            out.append((b, b.translated))
        for r in getattr(b, "runs", []) or []:
            if r.translated:
                out.append((r, r.translated))
        if b.table:
            for row in b.table.rows:
                for cell in row:
                    if getattr(cell, "translated", None):
                        out.append((cell, cell.translated))
    return out


def retranslate_foreign_runs(doc, tr, cfg: Config) -> int:
    """Re-translate leftover non-Latin runs in the translated text. Latin-script targets only.
    Returns the number of text fields changed. Best-effort: a failed batch leaves text as-is."""
    tgt = (cfg.target_lang or "").split("-")[0].lower()
    if tgt in _NON_LATIN_TARGETS:
        return 0
    fields = _fields(doc)
    runs = {m.group(0).strip() for _, t in fields for m in _FOREIGN.finditer(t)}
    runs = {r for r in runs if r}
    if not runs:
        return 0
    ordered = list(runs)
    try:
        trans = tr.translate_batch(ordered, cfg, src="auto")
    except Exception:
        return 0
    rmap = {r: (t or r).strip() for r, t in zip(ordered, trans)}
    n = 0
    for obj, t in fields:
        new = _FOREIGN.sub(lambda m: rmap.get(m.group(0).strip(), m.group(0)), t)
        if new != t:
            obj.translated = new
            n += 1
    return n
