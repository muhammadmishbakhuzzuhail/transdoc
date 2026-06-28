# Benchmark results

Reproducible numbers behind transdoc's quality claims. All figures are produced by the committed
harness; rerun and the `eval/history.jsonl` time-series records each run. **Read the caveats** — the
honest framing matters more than the numbers.

## Head-to-head: engines on FLORES-200 (free comparison)

`scripts/bench_vs_engines.py` translates the FLORES-200 English source through each engine and scores
against the FLORES gold reference with **sacrebleu corpus chrF** (higher = better). This is the *free*
head-to-head — our own runnable engines on a public gold benchmark. Paid DeepL / Google-Cloud are out
of scope (no API key, no cost); add them later behind the same harness if a key is available.

**FLORES-200 devtest, n = 15 sentences, EN → target, sacrebleu corpus chrF**

| target | google (default) | opusmt (offline, MIT) | nllb (offline, CC-BY-NC) |
|--------|-----------------:|----------------------:|-------------------------:|
| de     | **72.7**         | 67.6                  | 63.4 |
| hi     | **64.6**         | 28.1                  | 57.4 |
| id     | **68.9**         | 64.9                  | 62.8 |

Command:
```bash
cd backend && .venv/bin/python -m scripts.bench_vs_engines --no-comet \
    --engines google,opusmt,nllb --langs de,hi,id --n 15
```

### What this actually says

- **The default online engine (google) is genuinely strong** on these pairs — this validates the
  default rather than just asserting it.
- **The offline NMT path is a viable private/offline alternative** at a modest cost: NLLB trails
  google by ~5–9 chrF but runs fully offline (note NLLB is **CC-BY-NC — non-commercial**; for
  commercial use prefer Opus-MT / IndicTrans2).
- **Per-pair selection matters most for avoiding bad pairs.** Opus-MT is competitive on German
  (67.6) but collapses on Hindi (28.1 — it has no direct EN→HI model). This is exactly why
  **QE-gated engine selection** (`--engines ...`) exists: it would never pick Opus-MT for Hindi.
- IndicTrans2 (MIT, the documented Indic winner — reportedly +4–8 chrF over google on Indic) was not
  in this run; it's the obvious next candidate for Indic pairs.

### Caveats (do not over-read these numbers)

- **n = 15 is a smoke-sized sample.** Use n ≥ 200 (FLORES devtest is 1012) for any published claim.
- chrF is a surface metric. For a credible "more accurate than X" statement, add reference-based
  **COMET** (`--engine`/`--no-comet` toggles it) and report a *significance-tested* delta on the same
  test set + metric version — the COMET literature is unanimous that there's no absolute threshold.
- This compares engines, not the competitor *products* (DeepL Document / Google Cloud). Those need
  paid APIs and are deliberately excluded.

## Layout fidelity (BIoU)

`transdoc.eval.metrics.biou` (BabelDOC's metric) scores how faithfully the output preserves the
source page layout. On the synthetic fixtures the modes rank as expected — `layout` (overlay) ~50,
`reconstruct` ~25, `flow` ~26. For reference the BabelDOC paper reports BIoU 50.0 (BabelDOC) /
48.7 (PDFMathTranslate) / **19.8 (DeepL Document)**: layout preservation, not raw sentence quality,
is where document translators actually differ — and it's transdoc's headline differentiator.
