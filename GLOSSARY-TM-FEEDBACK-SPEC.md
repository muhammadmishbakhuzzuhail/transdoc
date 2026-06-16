# Glossary + Translation Memory + Feedback — Architecture Spec

Status: **DRAFT for review** (no code written yet). Date: 2026-06-16.
Decisions below were settled with the maintainer over four question rounds; this document is the
contract to review/revise **before** any implementation.

---

## 1. Motivation

A targeted code patch does not generalize. The trigger case: a 1917 German newspaper renders
`1 Mark 50 Pfennig` → `1 tanda 50 pfennig` ("Mark" = currency → "tanda" = sign). Two things were
tried and both were rejected or insufficient:

- A hardcoded currency stop-list (`{Mark, Pfennig, ...}`) — **rejected**: brittle, every new input
  has different units/languages; a fixed list never covers the space.
- Removing the auto-glossary pollution (language gate for noun-capitalizing languages) — **necessary
  but insufficient**: even with no glossary pinning, the engine *itself* mistranslates "Mark"
  in-context. Confirmed empirically.

Conclusion: the only thing that generalizes is a **system that learns** — a persistent, curated
glossary + translation memory fed by a human-in-the-loop correction loop, in the CAT-tool
tradition (Trados/DeepL), adapted to our local, CPU-only, no-server constraint. Currency becomes
one instance of "a term the user corrected once and the system now remembers", not special-cased
code.

This is also the maturity gap flagged in the architecture review: glossary is ephemeral per-run,
TM is exact-match-only with no provenance or correction path, and there is no feedback loop.

## 2. Scope & non-goals

In scope:
- Unified SQLite persistence for TM + glossary + corrections (single file).
- Glossary: 3-tier precedence, domain-scoped, protect→restore-target application, auto-glossary as
  ephemeral suggestion that persists only on confirmation.
- TM: exact + **fuzzy** (tiered reuse), provenance, confirmed-immune entries, correction override.
- Feedback loop: four capture mechanisms (CLI, edit-reimport, report column, web review UI).
- CLI management (`glossary` / `correct` / `tm`), TSV+JSON interop.
- Migration of the existing `tm.sqlite`.

Non-goals (deferred):
- Morphology/inflection-aware glossary substitution (boundary-aware substring only for now).
- TMX/XLIFF industry formats (TSV+JSON first).
- Cross-domain fuzzy reuse.
- Multi-user/sync/server features (stays local-single-user).

## 3. Decisions (resolved)

| Area | Decision |
|---|---|
| DB engine | **SQLite**, one file (fits local/no-server/no-Docker constraint; already used for TM) |
| DB location | `~/.local/share/transdoc/transdoc.db` (XDG data; **not** cache — glossary/corrections must survive `clear-cache`) |
| Migration | migrate existing `~/.cache/transdoc/tm.sqlite` entries into the new `tm` table |
| Scope granularity | per-`(src_lang, tgt_lang)` **+ domain** |
| Auto-glossary | **ephemeral suggestion**; persists to DB only when the user confirms |
| Glossary apply | **protect placeholder → restore TARGET rendering** (engine never sees the term) |
| TM fuzzy | tiered: **≥95% auto-apply, 75–95% suggest (flagged), <75% ignore** |
| Fuzzy vectors | **FTS5/trigram prefilter → embedding cosine rerank** (vectors as blobs + numpy); no external ext |
| Embedding model | sentence-transformer multilingual, CPU (e.g. LaBSE / paraphrase-multilingual-MiniLM); **maintainer provides model/path**, we design the interface |
| TM lifecycle | correction overrides the entry + marks it `confirmed` (immune to auto-overwrite); store provenance (engine, date, quality) |
| Precedence | **locked > user(`-g`) > confirmed > auto > fuzzy-TM > engine** |
| Domain fallback | unknown/auto domain → global scope; with a domain: that domain wins, then global; **no cross-domain** borrowing |
| Feedback capture | all four: CLI `correct`, edit-output→re-import, report correction column, web review UI |
| UI phasing | **backend store + REST API + CLI first**; web review UI is a later, separate PR |
| Interop | TSV (DeepL/CAT-style) + JSON export/import |
| Currency now | **leave it**; heals via the feedback loop once `correct` lands (no special patch, no seed list) |

## 4. Database schema (SQLite, DDL sketch)

```sql
PRAGMA journal_mode=WAL;

-- Translation memory: one row per (normalized source, src, tgt, domain).
CREATE TABLE tm (
  id          INTEGER PRIMARY KEY,
  src_norm    TEXT NOT NULL,          -- normalized source (lowercased, ws-collapsed) for exact key
  src_text    TEXT NOT NULL,          -- original source (for fuzzy display + rerank)
  src_lang    TEXT NOT NULL,
  tgt_lang    TEXT NOT NULL,
  domain      TEXT NOT NULL DEFAULT '',   -- '' = global
  tgt_text    TEXT NOT NULL,
  origin      TEXT NOT NULL,          -- 'engine' | 'correction'
  confirmed   INTEGER NOT NULL DEFAULT 0, -- 1 = human-confirmed, immune to auto-overwrite
  engine      TEXT,                   -- provenance
  quality     REAL,                   -- optional QE score
  hits        INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL,
  embedding   BLOB,                   -- float32 vector for fuzzy rerank (nullable until embedded)
  UNIQUE(src_norm, src_lang, tgt_lang, domain)
);
CREATE VIRTUAL TABLE tm_fts USING fts5(src_text, content='tm', content_rowid='id'); -- fuzzy prefilter

-- Glossary: term -> target rendering, scoped per language pair + domain.
CREATE TABLE glossary (
  id          INTEGER PRIMARY KEY,
  src_lang    TEXT NOT NULL,
  tgt_lang    TEXT NOT NULL,
  domain      TEXT NOT NULL DEFAULT '',
  term        TEXT NOT NULL,          -- source term
  rendering   TEXT NOT NULL,          -- target rendering (verbatim on restore)
  origin      TEXT NOT NULL,          -- 'user' | 'auto' | 'confirmed'
  locked      INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL,
  UNIQUE(src_lang, tgt_lang, domain, term)
);

-- Corrections (feedback audit + promotion source).
CREATE TABLE corrections (
  id          INTEGER PRIMARY KEY,
  src_text    TEXT NOT NULL,
  src_lang    TEXT NOT NULL,
  tgt_lang    TEXT NOT NULL,
  domain      TEXT NOT NULL DEFAULT '',
  bad_text    TEXT,                   -- what the system produced
  corrected   TEXT NOT NULL,          -- the human fix
  scope       TEXT NOT NULL,          -- 'segment' (->tm) | 'term' (->glossary)
  created_at  TEXT NOT NULL
);
```

Notes:
- `confirmed=1` rows are never overwritten by an engine result; only another correction updates them.
- `embedding` filled lazily by the embedder when present; absent → fuzzy falls back to FTS5/trigram
  score only (graceful degradation).

## 5. Resolution algorithm (per source segment)

```
1. glossary pass (locked > user > confirmed > auto), domain-then-global:
     mask each matching term -> [PH]; remember its TARGET rendering
2. TM exact: src_norm hit (domain, then global) -> use tgt_text (done)
3. TM fuzzy: FTS5/trigram candidates -> embedding cosine rerank
     >=95% -> auto-apply (flag 'fuzzy-auto'); 75-95% -> keep as suggestion, still call engine
4. engine: translate the protected text
5. restore [PH] -> TARGET renderings (glossary), then localize/numbers as today
6. write back; persist engine result to TM (origin='engine', confirmed=0) if cacheable
```
Precedence is enforced by the order of steps 1–4 and by `confirmed`/`locked` flags.

## 6. Module layout (proposed)

```
backend/src/transdoc/store/
  db.py         # connection, PRAGMA, schema creation + versioned migrations, XDG path
  tm.py         # TMStore: exact get/put, fuzzy search, provenance, confirm; replaces translate/memory.py
  glossary.py   # GlossaryStore: resolve(src,tgt,domain) -> ordered terms; add/list/rm; import/export
  feedback.py   # record correction -> promote to tm/glossary; report-diff import
  embed.py      # Embedder interface (load model from configured path); encode(texts)->vectors
```
`translate/base.py` calls `GlossaryStore.resolve(...)` + `TMStore` instead of the current
in-file glossary mining + `PersistentTM`. Auto-glossary mining stays in `base.py` but only emits
*suggestions* (written to `corrections`/a pending table or surfaced in the report) — never directly
to the `glossary` table.

## 7. CLI surface

```
transdoc glossary add  <term> <rendering> -s de -t id [--domain legal] [--lock]
transdoc glossary list [-s de -t id] [--domain ..]
transdoc glossary rm   <term> -s de -t id [--domain ..]
transdoc glossary export <file.tsv|.json> [-s de -t id]
transdoc glossary import <file.tsv|.json>
transdoc correct "<source>" "<fix>" -s de -t id [--domain ..] [--term]   # segment (default) or term
transdoc tm stats
transdoc tm purge [--unconfirmed] [--older-than 90d]
transdoc tm confirm "<source>" -t id        # promote an engine entry to confirmed
```
Existing `-g <glossary.json>` flag keeps working (loads into the per-run "user" tier).

## 8. Feedback mechanisms (all four)

1. **CLI `correct`** — fastest, headless. `--term` promotes to glossary; default promotes the
   segment to confirmed TM.
2. **Edit output → re-import** — `transdoc feedback import <edited_output> --against <original_output>`;
   diff aligned segments, capture changed ones as corrections. (parsing-tolerant; markdown first.)
3. **Report correction column** — the report gains an editable column; `feedback import <report>`
   reads filled rows.
4. **Web review UI** — side-by-side source||translation, inline edit, batch-confirm of
   auto-glossary suggestions and fuzzy suggestions. **Later PR** (REST API designed in PR-4 so the
   UI is a thin client).

Confirmation workflow: auto-glossary + 75–95% fuzzy results are surfaced as *suggestions*; the user
confirms via CLI (`tm confirm` / `glossary add`) or the review UI. Confirmed → persisted with the
right tier.

## 9. Migration

- On first run with the new code, if `~/.cache/transdoc/tm.sqlite` exists and the new DB has no `tm`
  rows, copy entries: old key `(norm, lang)` → `tm(src_norm=norm, tgt_lang=lang, src_lang='auto'?,
  domain='', origin='engine', confirmed=0)`. Old rows lack src_lang — store `src_lang=''` (unknown);
  exact-match lookup treats `''` as wildcard for legacy rows.
- Keep `TRANSDOC_TM_DISABLE` / `TRANSDOC_TM_PATH` env compatibility.

## 10. Config additions

```
auto_glossary: bool = True          # (exists) now means "mine SUGGESTIONS", never auto-persist
fuzzy_tm: bool = True               # enable fuzzy reuse
fuzzy_auto_threshold: float = 0.95
fuzzy_suggest_threshold: float = 0.75
embed_model: str | None = None      # path/name of the sentence-transformer; None -> fuzzy uses FTS5/trigram only
domain: str = "auto"                # (exists) scopes glossary/TM
```

## 11. PR sequencing (build order)

- **PR-0** (already written, pending decision): Fraktur OCR (`deu_frak` for German source) +
  auto-glossary **language gate** for noun-capitalizing langs. General correctness fixes,
  independent of this spec. → merge as-is, or fold in. *Needs maintainer call.*
- **PR-1** `store/db.py` + `store/tm.py` + migration; swap `PersistentTM` → `TMStore` (exact-match
  parity, no behavior change). Tests + green CI.
- **PR-2** `store/glossary.py` + protect→restore-target application + precedence; auto-glossary
  becomes suggestion-only. Wire into `translate/base.py`.
- **PR-3** `store/feedback.py` + CLI `correct` / `glossary` / `tm` + TSV/JSON interop.
- **PR-4** fuzzy TM: `embed.py` interface + FTS5 prefilter + rerank + tiered apply. (maintainer
  supplies the model.)
- **PR-5** REST feedback API (thin) — sets up the UI.
- **PR-6** web review UI (side-by-side, edit, batch-confirm).

Each PR: branch → test → ruff → CI green → squash-merge. Eval gates (`eval`, and the on-demand
scorecard) must stay green; add targeted tests per PR.

## 12. Open items for maintainer

1. **PR-0 disposition** — merge the Fraktur + language-gate fixes now, or fold into PR-2? → **done, merged #163.**
2. **Embedding model** — which sentence-transformer + where is it on disk (`embed_model` value)?
3. Confirm `~/.local/share/transdoc/transdoc.db` as the path (vs a project-local override).
4. Anything to add to non-goals (TMX/XLIFF, inflection) for a later milestone?

Status: PR-1 (store + TMStore, exact-match parity) merged #164.

---

# Quality architecture (imitate + modify) — areas A/E/C/D

Four areas to dissect from existing systems to raise translation/fidelity quality. Build order:
**A → E → C → D**. All engine options chosen are **zero-cost** (free). Document-level context needs
an LLM (NMT is segment-level); the chosen free engine is **Ollama local** (offline, private,
no-quota). Free online alternatives analyzed and kept as future pluggable backends: Gemini Flash
free-tier, OpenRouter `:free`, Groq.

**Scope lock (maintainer):**
- **Output format == input format.** Cross-format conversion (PDF→DOCX and vice-versa) is **skipped
  for now** — keep the document's own type (the `same-as-source` path). North-star "output ≡ input,
  only the language changes" is taken literally on format too. Cross-format is a later milestone.
- **LLM = one model, decided: Qwen2.5-7B-Instruct** (HF `Qwen/Qwen2.5-7B-Instruct`; Ollama
  `qwen2.5:7b`). Apache-2.0, 29+ languages incl. Indonesian; Q4_K_M ~4.7 GB fits the dev box
  (RTX 3050 6 GB / i5-13450HX 16-thread / 11 GB RAM, rest offloads to CPU). No per-run LLM choice.
  Free policy: **Google web NMT where it works; the local LLM only where Google falls short**
  (the hybrid QE-gate). DeepL's own models are proprietary/closed — nothing to reuse there.

## Area A — document-level, context-aware translation (Ollama LLM)

Problem: today every segment is translated independently by the Google web NMT, so cross-sentence
coherence, pronoun/reference, and terminology consistency drift. Imitate DeepL doc-mode / LLM
sliding-context; modify for our IR + local CPU + free Ollama.

Decisions (settled over three question rounds):

| Aspect | Decision |
|---|---|
| Engine role | **Hybrid via QE-gate**: NMT default, LLM only for low-QE / context-sensitive / hard segments. The QE gate depends on Area E, so the LLM engine is built first (usable as `-e ollama` / full), and the auto-gate is wired after E. |
| Context | **Sliding window: 2 previous (already-TRANSLATED, carried for consistency) + 2 following (source)**, read-only around the target segment |
| Alignment | **Numbered segments → structured JSON `{id: translation}`**; validate 1:1; mismatch → retry → hard-fail |
| Glossary | **prompt term instruction** (DeepL-style "use these renderings") **+ keep protect placeholders** for verbatim tokens (urls/numbers/codes) |
| Caching | **TM with a context-hash** — new `ctx` column (schema v2); NMT rows use `ctx=''`, LLM rows `ctx=hash(window)`. They coexist; exact-match NMT lookups filter `ctx=''` |
| Failure | **Retry 2× (backoff) → hard-fail** (explicit error; no silent NMT fallback) |
| Ollama | **temp=0** (deterministic → caching valid), host configurable (default `localhost:11434`, env/config override), `format=json`, request timeout |
| Batch | **Adaptive by token budget** — pack segments+windows up to a safe `num_ctx` fraction; IDs keep alignment |
| Prompt | inject **target lang + register + domain** (from the diagnose phase) + preservation rules ("keep formatting/placeholders, don't add/remove content, output JSON `{id: translation}`") |

Protocol impact: the current `Translator.translate_batch(texts)` is order-free (dedupe reorders +
uniquifies), which loses neighbors. Add a capability flag `doc_context = True` and a context-aware
entry point that receives the **ordered** segments so windows can be built; the dedupe/TM path adapts
to key on `(norm, ctx_hash)`.

PR breakdown for Area A:
- **PR-A1** Ollama engine + `doc_context` protocol + sliding-window + JSON alignment + config
  (`Engine.OLLAMA`, `ollama_host/model/num_ctx/timeout`, `llm_context_window=2`) + retry/hard-fail +
  glossary-prompt + protect. LLM always-fresh (no cache yet). Tests against a faked Ollama HTTP.
- **PR-A2** schema v2 `ctx` column + context-hash caching in TMStore; wire LLM caching.
- **PR-A3** (after Area E) hybrid QE-gate routing: NMT default, escalate weak segments to Ollama.

## Areas E / C / D — to be matured (question rounds) when reached

- **E** translation QA-check suite (imitate memoQ QA + COMET-QE): number/date mismatch, length-ratio,
  terminology adherence, missing placeholders/tags, untranslated — feeds the feedback loop + the
  A QE-gate.
- **C** reflow & text-expansion fidelity (imitate BabelDOC / Marker): adaptive font-scale / box-grow.
- **D** layout & reading-order (imitate Surya / PP-StructureV3 / Marker): stronger multi-column/figure
  reading order.
