# Benchmark results

Reproducible numbers behind transdoc's quality claims. All figures are produced by the committed
harness; rerun and the `eval/history.jsonl` time-series records each run. **Read the caveats** — the
honest framing matters more than the numbers.

## Head-to-head: engines on FLORES-200 (free comparison)

`scripts/bench_vs_engines.py` translates the FLORES-200 English source through each engine and scores
against the FLORES gold reference with **sacrebleu corpus chrF** (higher = better). This is the *free*
head-to-head — our own runnable engines on a public gold benchmark. Paid DeepL / Google-Cloud are out
of scope (no API key, no cost); add them later behind the same harness if a key is available.

**FLORES-200 devtest, n = 200 sentences, EN → target, sacrebleu corpus chrF**

| target | google (default) | opusmt (offline, MIT) | nllb (offline, CC-BY-NC) | indictrans |
|--------|-----------------:|----------------------:|-------------------------:|-----------:|
| de     | **70.2**         | 63.5                  | 62.8                     | n/a |
| hi     | **61.3**         | 34.0                  | 56.9                     | n/a |
| bn     | **56.8**         | 0.8                   | 56.6 †                   | n/a |
| id     | **72.4**         | 64.9                  | 68.0                     | n/a |

Command:
```bash
cd backend && .venv/bin/python -m scripts.bench_vs_engines --no-comet \
    --engines google,opusmt,nllb,indictrans --langs de,hi,bn,id --n 200
```

(An earlier n=15 smoke run gave de 72.7 / hi 64.6 / id 68.9 for google — consistent.)

**† The Bengali NLLB cell originally scored 0.8** — that run uncovered a real bug: `nllb.py`'s
FLORES-code map covered only 16 languages, so an unmapped target (bn, ta, ur, fa, tr, pl, …) silently
fell back to `eng_Latn` and NLLB returned the English source untranslated. **Fixed** (comprehensive
map + raise-on-unmapped-target, no silent passthrough); post-fix NLLB en→bn produces proper Bengali
(~56.6 chrF, in line with hi/id). This is exactly the kind of silent defect a head-to-head harness is
for. **indictrans** is `n/a` because IndicTrans2 needs the optional `[indic]` extra
(`pip install -e '.[indic]'`); install it to benchmark the documented Indic winner.

### What this actually says

- **The default online engine (google) is genuinely strong** on these pairs — this validates the
  default rather than just asserting it.
- **The offline NMT path is a viable private/offline alternative** at a modest cost: NLLB trails
  google by ~5–9 chrF but runs fully offline (note NLLB is **CC-BY-NC — non-commercial**; for
  commercial use prefer Opus-MT / IndicTrans2).
- **Per-pair selection matters most for avoiding bad pairs.** Opus-MT is competitive on German
  (63.5) but collapses on Hindi (34.0) and Bengali (0.8 — no usable EN→BN model). This is exactly why
  **QE-gated engine selection** (`--engines ...`) exists: it would never pick Opus-MT for those.
- IndicTrans2 (MIT, the documented Indic winner — reportedly +4–8 chrF over google on Indic) needs the
  `[indic]` extra to run; it's the obvious next candidate for Indic pairs once installed.

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
