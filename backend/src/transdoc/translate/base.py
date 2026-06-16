"""Translator interface + shared logic that every engine reuses.

The translate phase walks the IR: translatable blocks get their text translated (and table
cells), verbatim blocks are left untouched, and the glossary is enforced uniformly so one
source term maps to one target rendering everywhere.
"""

from __future__ import annotations

import re
from typing import Protocol

from ..config import Config
from ..ir import Block, Document


class Translator(Protocol):
    name: str

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        """Translate a list of strings. Order preserved, 1:1 with input."""
        ...


def _looks_untranslated(src: str, out: str) -> bool:
    """A substantial segment that came back byte-identical to its source probably wasn't
    translated (engine skipped/throttled it). Short or proper-noun-only spans legitimately
    stay the same, so require several real words before flagging."""
    if out.strip() != src.strip():
        return False
    return len(re.findall(r"[^\W\d_]{4,}", src)) >= 3


def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
    """Enforce term consistency. Longest terms first to avoid partial overlaps."""
    for term in sorted(glossary, key=len, reverse=True):
        if not term:
            continue
        repl = glossary[term]
        # Word-boundary match for ASCII alphanumeric terms so "cat" doesn't fire inside
        # "category". CJK / punctuation-edged terms have no \w boundary, so fall back to a
        # plain substring replace for those.
        if term.isascii() and term[0].isalnum() and term[-1].isalnum():
            text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", lambda _m, r=repl: r, text)
        elif term in text:
            text = text.replace(term, repl)
    return text


_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")                 # NASA, API, ISO9001
_PROPER = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")     # Hugging Face, United Nations
_CAP_WORD = re.compile(r"\b[A-Z][a-z]{2,}\b")                   # single Capitalized word
_WORD = re.compile(r"\b[a-zA-Z]{2,}\b")
# Common words that are Capitalized only because they start sentences — never proper nouns.
_CAP_STOP = {
    "The", "This", "That", "These", "Those", "There", "Then", "Thus", "However", "Therefore",
    "Moreover", "Although", "Because", "While", "When", "Where", "What", "Which", "Whereas",
    "After", "Before", "During", "Since", "Also", "And", "But", "For", "Each", "Every", "All",
    "Both", "Such", "They", "Their", "His", "Her", "Our", "Your", "Its", "It", "If", "In", "On",
    "At", "As", "An", "Article", "Everyone", "No", "One",
}


def _auto_glossary_terms(texts: list[str], min_count: int = 2) -> list[str]:
    """Mine recurring (>= min_count) proper nouns whose rendering is safe to pin document-wide:
    ALL-CAPS acronyms, and single Capitalized words that are NEVER seen lowercased ("Transdoc",
    "Photoshop"). Deliberately conservative — excluded: sentence-start stopwords; any word that
    also appears lowercase (common nouns inflect legitimately); and any word that sits inside a
    multi-word Capitalized run (pinning one word of a name in isolation could mistranslate it,
    e.g. "Face" -> "Visage" inside "Hugging Face"). Multi-word names are left to the user glossary."""
    from collections import Counter
    c: Counter = Counter()
    lowered: set[str] = set()
    run_words: set[str] = set()
    for t in texts:
        for m in _WORD.findall(t):
            if m.islower():
                lowered.add(m)
        for m in _PROPER.findall(t):
            run_words.update(m.split())        # part of a multi-word name -> don't pin in isolation
    for t in texts:
        for m in _ACRONYM.findall(t):
            c[m] += 1
        for m in _CAP_WORD.findall(t):
            if m not in _CAP_STOP and m.lower() not in lowered and m not in run_words:
                c[m] += 1
    return sorted((term for term, n in c.items() if n >= min_count), key=len, reverse=True)


def _collect_cells(table, items: list) -> None:
    """Collect translatable cell texts, recursing into nested tables."""
    for row in table.rows:
        for cell in row:
            if cell.text.strip():
                items.append((cell.text, cell))
            if cell.table:
                _collect_cells(cell.table, items)


def translate_document(doc: Document, tr: Translator, cfg: Config) -> None:
    """Translate the whole IR in place. Collects translatable strings, batches them,
    writes results back to blocks and table cells, then enforces the glossary."""
    target = cfg.require_target()
    glossary = dict(cfg.glossary)

    # 1) collect (block paragraphs + table cells)
    items: list[tuple[str, object]] = []  # (text, sink)
    for b in doc.blocks:
        if b.type.value == "table":
            # structured table -> translate each cell; a merged numeric table block (no
            # cells, from the PDF parser) is left verbatim so its grid survives.
            if b.table:
                _collect_cells(b.table, items)
            continue
        if b.is_translatable:
            items.append((b.text, b))
            # inline runs (mixed-style spans) translate per-run so styling survives; the
            # whole-block translation above still fills b.translated as the uniform fallback.
            for r in b.runs:
                if r.text.strip():
                    items.append((r.text, r))

    # DOCX section header/footer paragraphs translate too (kept off `blocks` so they render into
    # the output section's header/footer, not the body).
    for b in (*doc.headers, *doc.footers):
        if b.is_translatable:
            items.append((b.text, b))

    # PDF outline / bookmark titles translate too, so the navigable outline is in target lang.
    for e in doc.toc:
        if e.title.strip():
            items.append((e.title, e))

    if not items:
        return

    from .memory import PersistentTM, TranslationMemory
    from .protect import Protector

    texts = [t for t, _ in items]

    # 0) auto-glossary: mine repeated proper nouns (acronyms + multi-word Capitalized names) and
    #    pin ONE rendering for each across the whole document. Sentence MT translates each segment
    #    independently, so a product/org name can drift (measured: id "Transdoc" rendered
    #    differently in every context). Conservative — proper nouns only (common-noun inflection is
    #    legitimate), only when the engine is real (echo is non-cacheable), and only when the
    #    canonical rendering actually differs from the source. User glossary entries always win.
    if getattr(cfg, "auto_glossary", True) and getattr(tr, "cacheable", True):
        auto = [t for t in _auto_glossary_terms(texts) if t not in glossary]
        if auto:
            try:
                for term, ren in zip(auto, tr.translate_batch(auto, cfg, src=doc.source_lang)):
                    ren = (ren or "").strip()
                    if ren and ren != term:
                        glossary[term] = ren
            except Exception:
                pass            # auto-glossary is best-effort; never block the main translation

    # 1a) dedupe identical segments via TM -> translate each unique string once
    tm = TranslationMemory()
    unique, idx_map = tm.dedupe(texts)

    # 1b) cross-run cache: skip segments already translated for this target in any prior run.
    #     This is what keeps a free Google-web-endpoint service under the rate limit.
    ptm = PersistentTM.get()
    cached = ptm.get_many(unique, target) if ptm else {}
    todo = [u for u in unique if u not in cached]

    # 1c) protect verbatim tokens (urls/emails/numbers/dates/codes) on cache MISSES only
    protector = Protector(extra=list(glossary.keys()))
    protected, maps = [], []
    for u in todo:
        p, m = protector.protect(u)
        protected.append(p)
        maps.append(m)

    # 2) translate the protected misses, restore tokens, then fold cache hits back in.
    #    If the batch fails (one segment that every engine rejects/throttles would otherwise
    #    sink the whole document), degrade to per-segment: keep the source for the segments
    #    that still fail so they're flagged untranslated, not lost — the rest translate.
    if not protected:
        fresh = []
    else:
        try:
            fresh = tr.translate_batch(protected, cfg, src=doc.source_lang)
        except Exception:
            fresh = []
            for p in protected:
                try:
                    fresh.append(tr.translate_batch([p], cfg, src=doc.source_lang)[0])
                except Exception:
                    fresh.append(p)        # keep source -> flagged 'untranslated' downstream
    if cfg.localize:
        # Reformat numbers to the target locale while protected tokens are still [PH] tags,
        # so verbatim currency/dates/codes are not touched.
        from .localize import localize_numbers
        fresh = [localize_numbers(t, target) for t in fresh]
    fresh = [protector.restore(t, m) for t, m in zip(fresh, maps)]
    fresh_map = dict(zip(todo, fresh))
    # Only persist real translations. A no-op engine (echo) marks itself non-cacheable so its
    # "[id] ..." placeholder output never poisons the cross-run TM for later real runs.
    if ptm and fresh_map and getattr(tr, "cacheable", True):
        ptm.put_many(fresh_map, target)
    translated_unique = [cached.get(u) or fresh_map.get(u, u) for u in unique]

    # 3) scatter unique results back to every original position
    out = [translated_unique[idx_map[i]] for i in range(len(texts))]

    # 4) write back + glossary enforcement
    for (src_text, sink), translated in zip(items, out):
        translated = _apply_glossary(translated, glossary)
        if isinstance(sink, Block):
            sink.translated = translated
            sink.confidence.translation = sink.confidence.translation or 0.9
            if _looks_untranslated(src_text, translated):
                sink.flags["untranslated"] = (
                    "translation equals source — engine may have skipped this segment")
        else:  # Cell
            sink.translated = translated

    doc.target_lang = target
