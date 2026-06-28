# Eval harness

Turns "the output looks good" into measurable, reproducible numbers, and gates regressions in
CI by diffing against a saved baseline.

## Run

```bash
# score a corpus (echo engine = deterministic, no network)
python -m transdoc.eval.harness corpus/synthetic

# save a scorecard
python -m transdoc.eval.harness corpus/synthetic --out scorecard.json

# gate: exit 1 if any metric regressed vs the baseline
python -m transdoc.eval.harness corpus/synthetic --baseline scorecard.json
```

## Metrics (`transdoc.eval.metrics`)

| family       | metric                              | needs gold? | network? |
|--------------|-------------------------------------|-------------|----------|
| structure    | blocks, formulas, tables, cells, figures, reading-order monotonic | no | no |
| rendering    | overwrite (text-on-image), tiny (<6pt), overflow                  | no | no |
| layout       | **BIoU** (source↔output bbox-IoU, BabelDOC) — PDF→PDF only        | no | no |
| OCR / text   | CER, WER (builtin Levenshtein)      | `.gold.txt` | no |
| translation  | chrF (char n-gram F)                | `.ref.<lang>.txt` | yes (real engine) |

**BIoU** (layout fidelity) is the headline differentiator metric: the mean bounding-box IoU
between the source page and the translated output page, so it scores how faithfully layout is
preserved *through* translation with no gold reference. `layout` mode (overlay) scores highest,
`reconstruct` next, `flow` lowest (it reflows by design). For reference, the BabelDOC paper reports
BIoU 50.0 (BabelDOC) vs 48.7 (PDFMathTranslate) vs **19.8 (DeepL Document)** — layout preservation,
not raw sentence quality, is where document translators actually differ.

The structure + rendering metrics are **deterministic** with `--engine echo`, so they're the
CI-able core. They catch the class of regression that silently dropped the structured path to
the heuristic extractor: `formulas`/`tables` cratering, or reading order going non-monotonic.

## Gold sidecars (optional)

Place next to each input `<stem><ext>`:

- `<stem>.gold.txt` — plain-text ground truth → CER/WER of the **extracted** text.
- `<stem>.ref.<lang>.txt` — reference translation → chrF of the **translated** text.

## Regression rule (`diff_baseline`)

A run regresses if, for any document vs the baseline:

- a count in `blocks, formulas, tables, table_cells, figures` **dropped**, or
- a defect in `flagged, overwrite, tiny, overflow` **grew**, or
- reading order went from monotonic to non-monotonic, or
- chrF dropped more than `chrf_tol` (default 1.0), or
- **BIoU** dropped more than `biou_tol` (default 3.0) — a layout-fidelity regression, or
- the document now errors / went missing.

## Publishable numbers (sacrebleu) & the quality trend

The builtin `chrf()` is the harness's mean sentence-level char-F2 — dependency-free and good for
internal tracking, but **not** comparable to published figures. For any externally-cited number use
the sacrebleu helpers (`sacrebleu_chrf` / `sacrebleu_bleu` in `metrics.py`), which emit corpus-level
scores with a reproducible signature; `sacrebleu` is a dev/eval dependency and the helpers return
`None` if it isn't installed. `scripts.eval_translate` prints both side by side against FLORES-200.

A run's headline numbers are appended to `eval/history.jsonl` (the committed quality time-series),
so the trend — and the last-known numbers — live in the repo rather than a private notebook. Render
it any time:

```bash
cd backend && .venv/bin/python -m scripts.quality_dashboard          # markdown trend, last 20 runs
```

Note: these are **reference-free QE / chrF-vs-FLORES**, i.e. tracking our own pipeline over time —
not a head-to-head against a competitor's output. A credible "more accurate than X" claim must be a
*relative*, significance-tested comparison on the same test set + metric version (the COMET
literature is unanimous that there is no absolute cross-language threshold).

## Heavier validated tooling (not required)

The builtin metrics keep the harness dependency-free for CI. For deeper analysis the validated
references are `jiwer` (CER/WER), `sacrebleu` (BLEU/chrF/TER — now wired in as above),
`unbabel-comet` (neural COMET — model download, some checkpoints are CC-BY-NC) and TEDS for
table-structure similarity. Swap them in behind the same `metrics.py` signatures if you want them.
