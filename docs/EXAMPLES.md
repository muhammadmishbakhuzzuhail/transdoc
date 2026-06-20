# Examples gallery

Real **input → output** pairs produced by transdoc, so you can see what it does before running it.
Each example translates a non-English source **to English** with `--to same-as-source` (format
preserved). Source and output files are in [`examples/`](examples); the thumbnails show page 1.

> Reproduce any row:
> ```bash
> cd backend
> transdoc translate <source> --lang en --to same-as-source
> ```
> Quality numbers are reference-free COMET-Kiwi QE (mean over scored segments). Sources are the
> public-domain UN Universal Declaration of Human Rights (UDHR) plus one synthetic DOCX.

| Example | Source | Output (English) |
|---------|--------|------------------|
| **Arabic — RTL digital PDF** → English · QE ≈ 0.74<br>[source](examples/arabic.src.pdf) · [output](examples/arabic.en.pdf) | ![](examples/arabic.src.png) | ![](examples/arabic.en.png) |
| **Chinese — CJK digital PDF** → English · QE ≈ 0.78<br>[source](examples/chinese.src.pdf) · [output](examples/chinese.en.pdf) | ![](examples/chinese.src.png) | ![](examples/chinese.en.png) |
| **Hindi — scanned PDF (OCR)** → English · QE ≈ 0.75<br>[source](examples/hindi-scan.src.pdf) · [output](examples/hindi-scan.en.pdf) | ![](examples/hindi-scan.src.png) | ![](examples/hindi-scan.en.png) |
| **Multilingual DOCX** → English (round-trip)<br>[source](examples/mixed-docx.src.docx) · [output](examples/mixed-docx.en.docx) | ![](examples/mixed-docx.src.png) | ![](examples/mixed-docx.en.png) |

## What these show

- **Layout is preserved across scripts.** RTL Arabic and CJK Chinese reflow cleanly into English;
  the Wikipedia logo, the Eleanor-Roosevelt figure, and its caption stay in place (caption
  anchoring). Cross-script sources reflow (FLOW) instead of being force-fit into the source's
  per-glyph geometry.
- **Scanned documents work.** The Hindi example is an image-only PDF — OCR → translate → clean
  English output, no source text layer required.
- **In-place Office round-trip.** The DOCX keeps its headings, list, and table; only the language
  changes (the multilingual line is normalised to English).

## Notes & limits

- Quality is engine- and source-bound. Distant pairs (CJK/RTL → English) and noisy scans score
  lower than same-script pairs; very poor scans (faint historical manuscripts) remain OCR-limited.
- These are reference samples, not a benchmark. Run the [eval harness](DEVELOPMENT.md#evaluation-harness)
  for measured quality.

See also: [USAGE.md](USAGE.md) · [QUALITY.md](QUALITY.md) · [FIDELITY.md](FIDELITY.md)
