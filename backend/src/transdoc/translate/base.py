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
