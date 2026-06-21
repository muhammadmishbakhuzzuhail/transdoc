# Quality pipeline

transdoc layers several CPU/local quality stages on top of the raw translation engine. This
document explains what each stage does, **when it runs**, and **how to switch it on**. For the flag
and field names, see [CONFIGURATION.md](CONFIGURATION.md); for the end-to-end stage order, see
[ARCHITECTURE.md](ARCHITECTURE.md).

> **Scope:** translation/OCR *quality* features. Layout fidelity (reconstruct/overlay/flow) is in
> [FIDELITY.md](FIDELITY.md); engine choice is in [TRANSLATION.md](TRANSLATION.md).

---

## Stage map

```
extract → reading-order → repair → diagnose → translate → residual → align
        → consistency → QA → quality(QE) → escalate → regenerate → verify → review
```

| Stage | Switch | Default | What it does |
|-------|--------|---------|--------------|
| Reading-order | `reading_order_engine` | `xycut` | Orders blocks into human reading order before translation |
| OCR repair | `repair` | off | LLM fixes obvious OCR errors in low-confidence blocks |
| Residual cleanup | *(automatic)* | on | Re-translates leftover non-Latin runs for a Latin target |
| Style alignment | `align_styles` / UI "Style alignment" | on (UI) | Carries bold/italic across translated run boundaries |
| Consistency | `consistency` / `--consistency` | on | One translation per identical source string |
| Quality (QE) | `quality_check` / `-q` / UI "Quality flags" | on (UI) | Reference-free COMET-Kiwi score + weak-segment flags |
| Escalate | `escalate` / `--escalate` | off | LLM re-translates QE-weak segments with doc context |
| Verify | `verify` / `--verify` | off | Re-extracts the output and diffs structure vs source |

---

## Quality estimation (COMET-Kiwi)

Reference-free quality estimation scores every translated segment **without** needing a reference
translation, using the COMET-Kiwi model (`Unbabel/wmt22-cometkiwi-da`). Segments scoring below
`qe_threshold` (default `0.75`) are flagged in the report and the `/api/analysis` payload.

- **Enable:** `-q` (CLI) · `quality` form field (API, **default on**) · "Quality flags" (UI, on).
- **Tune:** `qe_threshold` (flag/escalate cutoff), `flag_threshold` (QA cutoff). See
  [CONFIGURATION.md](CONFIGURATION.md).
- COMET runs on GPU when available and is released between phases to respect the 6 GB VRAM ceiling.

## Escalation (QE-gated LLM re-translation)

With `--escalate`, segments the QE flags as weak are re-translated by the **local doc-context LLM**
(Ollama Gemma), which sees a sliding window of neighbouring segments (`llm_context_window`) for
coherence. This is a hybrid: cheap engine first, expensive LLM only where it helps.

- **Enable:** `--escalate` (CLI). Requires a running Ollama with `ollama_model` (default
  `gemma2:9b`). CLI-only by design.

## Style alignment (word-alignment style transfer)

Inline styling (bold/italic/colour) lives on *runs* in the source. After translation the run
boundaries shift, so naive copying smears styling. The aligner computes a word alignment
(awesome-align algorithm on multilingual BERT) and redistributes run styles onto the correct target
words.

- **Enable:** `align_styles` — `--align/--no-align` (CLI, **default on**), the `align` form field
  (API), and "Style alignment" (UI).

## Reading-order normalisation

Before translation, blocks are ordered into human reading order. The default `xycut` engine is a
deterministic recursive-whitespace (XY-cut) cut that scored a perfect reading-order tau in
evaluation. `surya` is available as an alternative but needs the Surya stack and is not the default.

- **Configure:** `reading_order_engine` (config-only).

## OCR repair

For scanned input, `repair` runs an LLM pass that conservatively fixes obvious OCR errors **only in
low-confidence blocks**, with hallucination guards (rejects ballooned output) and a logged audit
trail (`doc.repairs`). It never invents text.

- **Enable:** `--repair` (CLI) or the `repair` form field (API). Requires Ollama.

## Residual non-Latin cleanup

When a document declared as one language contains inline spans of another script (e.g. an English
PDF with a Chinese or Arabic quotation), the engine often leaves those spans untranslated. For a
**Latin-script target**, a residual pass detects the leftover non-Latin runs and re-translates each
with autodetection. Skipped when the target itself is non-Latin (foreign script is expected there).

- **Automatic** for Latin targets; no switch.

## Verify

`--verify` re-extracts the rendered output and diffs its structure (block/segment counts, layout)
against the source, catching regressions where rendering dropped or mangled content.

---

## Feedback flywheel

Corrections compound. A fix recorded with `transdoc correct` (or imported via
`transdoc feedback import` from a `--review` sidecar) becomes a **confirmed TM entry** (whole
segment) or an **authoritative glossary entry** (`--term`). On later documents:

- **TM** reuses confirmed translations exactly, and near-identical ones via fuzzy matching
  (`fuzzy_tm`, thresholds `fuzzy_auto_threshold` / `fuzzy_suggest_threshold`).
- **Glossary** pins terminology (auto-mined repeated proper nouns via `auto_glossary`, plus your
  locked terms).
- **Few-shot** (`few_shot`) injects your most similar confirmed corrections as LLM exemplars on the
  LLM path.

The persistent store lives at `~/.local/share/transdoc/transdoc.db` (override with
`TRANSDOC_DB_PATH`). A cache HIT skips re-translation — set `TRANSDOC_TM_DISABLE=1` to verify code
changes a cached entry would otherwise mask. See [USAGE.md](USAGE.md#3-terminology--feedback-glossary--tm--corrections).

---

See also: [USAGE.md](USAGE.md) · [CONFIGURATION.md](CONFIGURATION.md) · [FIDELITY.md](FIDELITY.md)
