# Test corpus

Input documents for the pipeline. Binaries are git-ignored (only this README and the small
structure baseline JSON are tracked) and reproducible with the scripts below. Two trees by
provenance:

> **Regression gate:** `baseline_real.json` (tracked) freezes parse-derived structure metrics
> (blocks / tables / cells / figures / reading-order) for the deterministic digital docs under
> `real/`. After fetching the corpus, run `make eval-real` to gate an extraction change against
> it; rebuild it with `make eval-real-baseline` after an *intended* change. OCR-only dirs
> (`full_image/`, `scanned_pdf/`) and font-sensitive render metrics are excluded so the gate is
> reproducible without network/OCR. It is local/opt-in — CI gates the committed synthetic
> fixtures only.
>
> **OCR accuracy (CER/WER):** `make eval-ocr` rasterizes the text-bearing UDHR PDFs
> (English/French/German/Spanish/Portuguese/Russian/Greek) to image-only "scans", OCRs them, and
> scores against the source text layer — exact, reproducible ground truth, no manual labels.
> Tesseract baseline mean ≈ 2% CER / 9% WER; `make eval-ocr` then `--layout auto` for the
> PP-StructureV3 path.
>
> **LLM-as-judge (no labels needed):** `make eval-judge ARGS="<files>"` has Claude vision score
> the extraction against the source image — text fidelity / completeness / structure / reading
> order, plus the specific content missed or hallucinated. Automates the manual vision-QA audit;
> needs `ANTHROPIC_API_KEY` + the `[llm]` extra (online, costs tokens).
>
> **Translation quality (chrF vs FLORES-200):** `make eval-translate ARGS="--n 100 fr de ja ar"`
> translates the FLORES-200 English dev set through the engine and scores against the
> professional reference with chrF, per language (15 langs across 7 scripts by default).
> Downloads FLORES-200 on first run (set `FLORES_DIR` to reuse); online (the engine is online).
> Note: single-reference chrF saturates on legitimate paraphrase — use it for tracking the
> pipeline over time, not as an absolute quality bar.
>
> **Entity preservation:** `make eval-preserve ARGS="--show fr ar ja"` checks that numbers, URLs,
> emails, dates, prices, and codes survive translation verbatim (the accuracy that matters for a
> document translator). Runs curated cases through the full translate path; online. This eval
> drove the protect.py currency/percent/time/#-code patterns (mean preservation 86% → 98%).

## `real/` — real-world downloads
Messy, no ground truth → integration / quality stress testing.
Reproduce with `scripts/fetch_corpus.sh` (+ `scripts/fetch_commons_images.py` for
`real/full_image/`).

| folder | contents |
|--------|----------|
| `digital_text/` | arXiv papers (Attention, BERT) — clean digital PDFs with tables/figures |
| `digital_pdf/`  | minimal + pdflatex fixtures |
| `forms/`        | IRS 1040 / W-9 (AcroForm + dotted-leader layout) |
| `full_image/`   | photos/scans of manuscripts, newspapers, constitutions (hard OCR) |
| `multilingual/` | UDHR in 16 languages (Latin, RTL, CJK, Devanagari, Cyrillic, Greek) |
| `office/`       | PowerPoint sample |
| `scanned_pdf/`  | real scanned UDHR (Hindi, Thai) |

## `synthetic/` — generated, known ground-truth
Deterministic fixtures with a known expected result. Regenerate with
`.venv/bin/python scripts/make_samples.py`.

| folder | contents |
|--------|----------|
| `image_only/`  | text rendered to PNG per script (ar/en/hi/ja/ko/ru/zh) |
| `photo/`       | skewed/low-quality photo of rendered text |
| `docx/`,`odt/` | `structured.*` — known headings, lists, table |
| `scanned_pdf/` | UDHR English/Russian rasterized to image-only PDF |

> Tests do not depend on these paths — they generate their own fixtures. This corpus is for
> manual/quality evaluation and benchmarking.
