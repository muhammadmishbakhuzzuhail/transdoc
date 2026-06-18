"""Translator interface + shared logic that every engine reuses.

The translate phase walks the IR: translatable blocks get their text translated (and table
cells), verbatim blocks are left untouched, and the glossary is enforced uniformly so one
source term maps to one target rendering everywhere.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from ..config import Config
from ..ir import Block, Document, Run


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


def _restore_edge_ws(src: str, out: str) -> str:
    """Re-apply the source run's leading/trailing whitespace to its translation. Engines strip edge
    whitespace, which glues adjacent inline runs together when they're concatenated
    ("international " + "Declaration" -> "internasionalDeklarasi"). A run with no edge space (a
    styled mid-word like "Wiki"|"pedia") stays glued, as it should."""
    if not out.strip():
        return out
    lead = src[:len(src) - len(src.lstrip())]
    trail = src[len(src.rstrip()):]
    return f"{lead}{out.strip()}{trail}"


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


def _resolve_glossary(cfg: Config, src_lang: str, tgt_lang: str) -> tuple[dict[str, str], set[str]]:
    """Build the term→rendering map for this run plus the set of locked terms, merging the persisted
    glossary with the per-run ``-g`` flag. Precedence: ``locked > user(-g) > confirmed > auto`` — the
    persisted store resolves its own tiers, then ``-g`` overlays as an ephemeral user tier that wins
    over everything EXCEPT locked entries. Domain comes from ``cfg.domain`` ('' / 'auto' = global)."""
    merged: dict[str, str] = {}
    locked: set[str] = set()
    from ..store.glossary import GlossaryStore
    gs = GlossaryStore.get()
    if gs is not None and src_lang and tgt_lang:
        domain = "" if cfg.domain in ("", "auto") else cfg.domain
        merged, locked = gs.resolve(src_lang, tgt_lang, domain)
    for term, rendering in cfg.glossary.items():     # -g flag: ephemeral user tier, below locked
        if term not in locked:
            merged[term] = rendering
    return merged, locked


def _protected_tokens_match(a: str, b: str) -> bool:
    """True if two sources carry the SAME verbatim tokens (numbers, codes, dates, currency, ...).
    The auto-apply safety gate: a near-identical past source whose protected tokens are unchanged is
    safe to reuse; if a number/code differs, the past translation would carry the wrong value."""
    from .protect import Protector
    p = Protector()
    _, ma = p.protect(a)
    _, mb = p.protect(b)
    return sorted(ma.values()) == sorted(mb.values())


def _fuzzy_reuse(ptm, todo: list[str], target: str, src_lang: str, cfg: Config,
                 glossary: dict[str, str], doc) -> tuple[dict[str, str], set[str]]:
    """For each cache-miss segment, look for a near-identical / similar past translation. Returns
    ``(fuzzy_hits, suggestion_sources)``: ``fuzzy_hits`` maps a source to a reused (glossary-applied)
    translation to auto-apply; ``suggestion_sources`` is the set of sources surfaced as review
    suggestions (engine still translates them). Records suggestions on ``doc.fuzzy_suggestions``."""
    hits: dict[str, str] = {}
    sugg: set[str] = set()
    if not (getattr(cfg, "fuzzy_tm", True) and ptm and todo
            and hasattr(ptm, "fuzzy_search")):
        return hits, sugg
    from ..store.embed import Embedder
    from ..store.tm import lexical_ratio
    embedder = Embedder.get(getattr(cfg, "embed_model", None))
    auto_t = getattr(cfg, "fuzzy_auto_threshold", 0.95)
    sugg_t = getattr(cfg, "fuzzy_suggest_threshold", 0.75)
    for u in todo:
        cands = ptm.fuzzy_search(u, target, src_lang=src_lang, embedder=embedder,
                                 min_score=sugg_t)
        if not cands:
            continue
        msrc, mtgt, score = cands[0]
        # Auto-apply only when the strings are near-identical AND protected tokens are unchanged —
        # regardless of the (possibly looser, semantic) embedding score.
        if (score >= auto_t and lexical_ratio(u, msrc) >= auto_t
                and _protected_tokens_match(u, msrc)):
            # Reuse the past translation verbatim (its tokens already match), then enforce glossary.
            hits[u] = _apply_glossary(mtgt, glossary)
        elif score >= sugg_t:
            sugg.add(u)
            doc.fuzzy_suggestions.append((u, msrc, mtgt, round(float(score), 3)))
    return hits, sugg


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
# Languages that capitalize EVERY common noun (not just proper nouns). There, an initial capital
# carries no proper-noun signal, so the single-Capitalized-word heuristic below would mine ordinary
# nouns ("Mark", "Posten", "Zeitung") and pin a wrong standalone rendering that overrides their
# correct in-context translation. Skip that heuristic for these source languages — only the
# language-independent ALL-CAPS acronym pass runs. (German-noun-capitalization audit)
_NOUN_CAPS_LANGS = {"de", "lb"}        # German, Luxembourgish (historically also Danish pre-1948)


def _auto_glossary_terms(texts: list[str], min_count: int = 2,
                         src: str | None = None) -> list[str]:
    """Mine recurring (>= min_count) proper nouns whose rendering is safe to pin document-wide:
    ALL-CAPS acronyms, and single Capitalized words that are NEVER seen lowercased ("Transdoc",
    "Photoshop"). Deliberately conservative — excluded: sentence-start stopwords; any word that
    also appears lowercase (common nouns inflect legitimately); and any word that sits inside a
    multi-word Capitalized run (pinning one word of a name in isolation could mistranslate it,
    e.g. "Face" -> "Visage" inside "Hugging Face"). Multi-word names are left to the user glossary.

    The single-Capitalized-word pass assumes an initial capital signals a proper noun — true for
    English/French/Spanish/Indonesian/... but FALSE for German/Luxembourgish, which capitalize every
    common noun. For those source languages it is skipped (it would pin ordinary nouns to a wrong
    standalone rendering); only the language-independent acronym pass runs there."""
    from collections import Counter
    c: Counter = Counter()
    lowered: set[str] = set()
    run_words: set[str] = set()
    cap_words_signal_proper = (src or "").split("-")[0].lower() not in _NOUN_CAPS_LANGS
    for t in texts:
        for m in _WORD.findall(t):
            if m.islower():
                lowered.add(m)
        for m in _PROPER.findall(t):
            run_words.update(m.split())        # part of a multi-word name -> don't pin in isolation
    for t in texts:
        for m in _ACRONYM.findall(t):
            c[m] += 1
        if not cap_words_signal_proper:
            continue
        for m in _CAP_WORD.findall(t):
            if m not in _CAP_STOP and m.lower() not in lowered and m not in run_words:
                c[m] += 1
    return sorted((term for term, n in c.items() if n >= min_count), key=len, reverse=True)


def _ctx_hash(texts: list[str], i: int, w: int) -> str:
    """Stable hash of segment i's SOURCE neighbour window (w before + w after, excluding i itself).
    The cache key for context-aware LLM translation: same segment + same neighbours -> same key, so
    a deterministic re-run hits the cache, while a different context translates afresh. '' when w=0."""
    if w <= 0:
        return ""
    before = texts[max(0, i - w):i]
    after = texts[i + 1:i + 1 + w]
    raw = "\x00".join([*before, "\x01", *after])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


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
    glossary, locked = _resolve_glossary(cfg, doc.source_lang or "", target)

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
    #    The mined terms are applied THIS run for intra-document consistency but are NOT persisted to
    #    the glossary table — they are recorded as *suggestions* (pending queue + report) for the user
    #    to confirm; only a confirmation (PR-3) promotes a suggestion to an applied entry (PR-2).
    if getattr(cfg, "auto_glossary", True) and getattr(tr, "cacheable", True):
        auto = [t for t in _auto_glossary_terms(texts, src=doc.source_lang) if t not in glossary]
        if auto:
            suggestions: list[tuple[str, str]] = []
            try:
                for term, ren in zip(auto, tr.translate_batch(auto, cfg, src=doc.source_lang)):
                    ren = (ren or "").strip()
                    if ren and ren != term:
                        glossary[term] = ren            # apply this run (document-wide consistency)
                        suggestions.append((term, ren))
            except Exception:
                pass            # auto-glossary is best-effort; never block the main translation
            if suggestions:
                doc.glossary_suggestions = [(t, r, "auto") for t, r in suggestions]
                from ..store.glossary import GlossaryStore
                gs = GlossaryStore.get()
                if gs is not None and doc.source_lang:
                    sug_domain = "" if cfg.domain in ("", "auto") else cfg.domain
                    gs.add_suggestions(suggestions, doc.source_lang, target, sug_domain)

    # doc-context engines (e.g. the Ollama LLM) translate the ORDERED segments with a sliding window
    # of translated neighbours, so coherence + terminology hold across the document. The engine
    # HARD-FAILS on error (raises) rather than silently keeping the source. Caching is keyed by a
    # hash of each segment's SOURCE neighbour window (context-hash, PR-A2): the same segment in a
    # different context caches separately, and a re-run of the same document (deterministic, temp=0)
    # is a full cache hit. Translation needs the neighbours, so when anything is missing the whole
    # ordered list is (re)translated and every segment stored — partial mid-document reuse is skipped.
    if getattr(tr, "doc_context", False):
        src_lang = doc.source_lang or ""
        ctx_domain = "" if cfg.domain in ("", "auto") else cfg.domain
        w = max(0, cfg.llm_context_window)
        ctxs = [_ctx_hash(texts, i, w) for i in range(len(texts))]
        ptm = PersistentTM.get() if getattr(tr, "cacheable_context", True) else None
        cached = ptm.get_segments(list(zip(texts, ctxs)), target, src_lang, ctx_domain) if ptm else {}
        if all((texts[i], ctxs[i]) in cached for i in range(len(texts))):
            out = [cached[(texts[i], ctxs[i])] for i in range(len(texts))]
        else:
            protector = Protector(extra=list(glossary.keys()), renderings=glossary)
            protected, maps = [], []
            for t in texts:
                p, m = protector.protect(t)
                protected.append(p)
                maps.append(m)
            seg = tr.translate_segments(protected, cfg, src=doc.source_lang)
            if cfg.localize:
                from .localize import localize_numbers
                seg = [localize_numbers(t, target) for t in seg]
            out = [protector.restore(t, m) for t, m in zip(seg, maps)]
            if ptm:
                ptm.put_segments([(texts[i], ctxs[i], out[i]) for i in range(len(texts))],
                                 target, src_lang, ctx_domain)
    else:
        # 1a) dedupe identical segments via TM -> translate each unique string once
        tm = TranslationMemory()
        unique, idx_map = tm.dedupe(texts)

        # 1b) cross-run cache: skip segments already translated for this target in any prior run.
        #     This is what keeps a free Google-web-endpoint service under the rate limit.
        ptm = PersistentTM.get()
        cached = ptm.get_many(unique, target) if ptm else {}
        todo = [u for u in unique if u not in cached]

        # 1b-fuzzy) reuse a near-identical past translation (PR-4). A high-scoring match whose text is
        #     near-identical AND whose protected tokens (numbers/codes/dates) are unchanged is safe to
        #     auto-apply (skip the engine) — this is the CAT-tool exact/placeable behaviour. A weaker
        #     (semantic) match is surfaced as a review suggestion; the engine still translates it. The
        #     embedding model only powers the suggestion ranking — auto-apply always requires lexical
        #     near-identity, so a semantically-similar-but-different sentence is never silently reused.
        fuzzy_hits, fuzzy_sugg_src = _fuzzy_reuse(ptm, todo, target, doc.source_lang or "",
                                                  cfg, glossary, doc)
        todo = [u for u in todo if u not in fuzzy_hits]

        # 1c) protect verbatim tokens (urls/emails/numbers/dates/codes) on cache MISSES only
        protector = Protector(extra=list(glossary.keys()), renderings=glossary)
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
                        fresh.append(p)    # keep source -> flagged 'untranslated' downstream
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
        translated_unique = [cached.get(u) or fuzzy_hits.get(u) or fresh_map.get(u, u)
                             for u in unique]

        # 3) scatter unique results back to every original position
        out = [translated_unique[idx_map[i]] for i in range(len(texts))]

    # 4) write back + glossary enforcement
    fuzzy_hits = locals().get("fuzzy_hits", {})
    fuzzy_sugg_src = locals().get("fuzzy_sugg_src", set())
    for (src_text, sink), translated in zip(items, out):
        translated = _apply_glossary(translated, glossary)
        if isinstance(sink, Block):
            sink.translated = translated
            sink.confidence.translation = sink.confidence.translation or 0.9
            if _looks_untranslated(src_text, translated):
                sink.flags["untranslated"] = (
                    "translation equals source — engine may have skipped this segment")
            if src_text in fuzzy_hits:
                sink.flags["fuzzy_auto"] = "reused a near-identical past translation"
            elif src_text in fuzzy_sugg_src:
                sink.flags["fuzzy_suggest"] = "a similar past translation exists (see report)"
        else:  # Cell or Run
            if isinstance(sink, Run):
                translated = _restore_edge_ws(src_text, translated)
            sink.translated = translated

    doc.target_lang = target
