# Test corpus

Input documents for the pipeline. Binaries are git-ignored (only this README is tracked) and
reproducible with the scripts below. Two trees by provenance:

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
