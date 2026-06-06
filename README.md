# transdoc — Document Intelligence & Translation Agent

Translate documents of **any** form to **any** language while **preserving layout**.
Not just translation — it diagnoses, reconstructs (OCR repair), translates, verifies, and
regenerates a clean, faithful document plus a full report.

Open-source alternative combining **DeepL-style translation + iLovePDF-style document
tooling + OCR-to-editable-document**, built on a format-agnostic Intermediate
Representation (IR) so any input maps to any output.

## Why it's different
- **Layout-preserving translation.** Two fidelity modes: `flow` (clean editable output for
  DOCX/MD) and `layout` (visual overlay that keeps the original page geometry — translate a
  PDF and it still looks like the original). Most open-source tools can't do the latter.
- **Any input.** Digital PDF, scanned PDF, photos, DOCX, ODT, legacy DOC, images.
- **Any script.** Latin, Arabic (RTL), CJK, Cyrillic, Devanagari, Thai — full Noto coverage.
- **Never invents, never drops.** Uncertain spans are flagged, not silently smoothed over.

## Architecture
```
INGEST → EXTRACT → OCR(if needed) → DIAGNOSE → [IR] → TRANSLATE → REGENERATE → REPORT
                                                 ↑ glossary + TM + confidence
```
The **IR** (`src/transdoc/ir.py`) is the single canonical model. Every extractor writes IR;
every renderer reads IR; translation edits IR in place. Swap any OCR/translation engine or
output format without touching the rest.

## Stack (see `docs/RESEARCH.md` for the verified rationale)
| Layer | Default | Fallback |
|-------|---------|----------|
| OCR + layout | Surya OCR 2 (GPU, 91 langs) | Tesseract (CPU) |
| PDF parse | PyMuPDF | — |
| Office parse | python-docx · odfpy · LibreOffice | — |
| Translate | OpenRouter LLM (deepseek/qwen/gemma/llama, failover) | Anthropic · NLLB-200 (non-commercial) · Argos (commercial-safe) |
| Regenerate | PyMuPDF `insert_htmlbox` overlay · python-docx | Markdown |

> ⚠️ NLLB-200 is **CC-BY-NC** (non-commercial). For commercial use pick Argos/LibreTranslate
> or the Anthropic engine.

## Install
```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e .                 # core (CPU path)
pip install -e ".[surya]"        # GPU OCR
pip install -e ".[nmt]"          # offline NLLB
pip install -e ".[llm]"          # Anthropic engine
```

## Usage
```bash
transdoc translate input.pdf --lang id --to docx        # PDF → translated Word
transdoc translate scan.png  --lang en --ocr tesseract  # image → OCR → translate
transdoc translate doc.pdf   --lang ar --to pdf -f layout  # layout-preserving overlay
transdoc convert  in.pdf     --to docx                   # OCR/convert only, no translation
transdoc diagnose input.pdf                              # profile only
```

## Status
Early. Core pipeline + IR + extractors (PDF/DOCX/ODT/image/text) + OCR (Tesseract/Surya)
+ translate (echo/anthropic/nllb/argos) + regenerate (md/docx/pdf) + report are in place.
Test corpus under `documents/` (real downloads) and `samples/` (synthetic ground-truth).

## License
Apache-2.0 (code). Bundled model weights carry their own licenses — see above.
