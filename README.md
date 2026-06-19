# transdoc — Document Intelligence & Translation Agent

Translate documents of **any** format into **any** language while **preserving layout**. transdoc
diagnoses, reconstructs (OCR repair), translates, verifies, and regenerates a clean, faithful
document — plus a full report. Think DeepL-style translation + iLovePDF-style document tooling +
OCR-to-editable-document, on a **CPU-first**, local machine.

It is built on a format-agnostic **Intermediate Representation (IR)**: any input maps to the IR,
translation edits the IR, any renderer turns the IR back into a document — so you can swap engines,
OCR backends, or output formats without touching the rest.

---

## Quickstart

```bash
# 1. Setup (first time)
make setup                  # backend .venv + frontend deps

# 2. Run the web UI + REST API
cd backend
source .venv/bin/activate
python server.py            # → http://127.0.0.1:8000   (API docs at /docs)
```

Open <http://127.0.0.1:8000>, upload a document, pick a target language, download the translation.

Prefer the command line?

```bash
cd backend && source .venv/bin/activate
transdoc translate report.pdf --lang id --to docx     # PDF → translated Word
```

→ Full run guide (all formats, CLI, REST API): **[docs/USAGE.md](docs/USAGE.md)**

---

## Features

- **Any input.** Digital PDF, scanned PDF, photos, DOCX, ODT, legacy DOC, PPTX, XLSX, EPUB,
  subtitles, images.
- **Any script.** Latin, Arabic (RTL), CJK, Cyrillic, Devanagari, Thai — full Noto coverage.
- **Layout-faithful PDF.** Auto-detects real **AcroForm forms** and renders them with an overlay
  (every line/box/checkbox kept); reflowable documents are rebuilt at the source page size with
  blocks in place. `-f flow` forces clean single-column reflow; `-f layout` forces overlay.
- **In-place Office round-trip.** DOCX/PPTX/XLSX/EPUB/SRT/VTT keep all original formatting.
- **Measured translation.** Default engine is **Google** (benchmark winner, chrF 85.1, CPU-only,
  no model); offline/private NMT (`-e nllb`) and local-LLM (`-e ollama`) engines are selectable.
- **A real quality pipeline.** Reference-free QE (COMET-Kiwi), LLM escalation of weak segments,
  word-alignment style transfer, reading-order normalisation, OCR repair, and a learning feedback
  flywheel (glossary + translation memory). → [docs/QUALITY.md](docs/QUALITY.md)
- **Never invents, never drops.** Uncertain spans are flagged, not silently smoothed over.

---

## Documentation

| Document | What's in it |
|----------|--------------|
| [docs/USAGE.md](docs/USAGE.md) | Running transdoc: web UI, CLI (every command + flag), REST API, examples per input type |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | Every config field, all engines, all environment variables |
| [docs/QUALITY.md](docs/QUALITY.md) | The quality pipeline: QE, escalation, alignment, OCR repair, feedback flywheel |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Dev setup, tests, the evaluation harness, the example corpus, code layout |
| [docs/EXAMPLES.md](docs/EXAMPLES.md) | Input → output gallery (preview of real results) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline architecture and the IR |
| [docs/FIDELITY.md](docs/FIDELITY.md) | Layout-fidelity strategy (reconstruct / overlay / flow) |
| [docs/TRANSLATION.md](docs/TRANSLATION.md) | Engine selection, the benchmark, licensing |
| [docs/RESEARCH.md](docs/RESEARCH.md) · [docs/RISKS.md](docs/RISKS.md) | Verified rationale and known limits |

```
backend/    Python package (transdoc): pipeline, CLI, FastAPI API, tests, scripts
frontend/   React UI (Vite + TypeScript + Tailwind + shadcn-style)
docs/        documentation + design notes
```

---

## Scope & limits

- **Personal, local, non-commercial.** Not distributed or commercialised, so software/model
  licenses are not a constraint here — AGPL (PyMuPDF) and CC-BY-NC weights (NLLB-200, Surya) are all
  fair game. The only goals are **maximum fidelity and quality on a CPU-only machine**.
- **North star:** output ≡ input, only the language changes. Cross-format conversion (e.g. PDF→DOCX
  as a *feature*) is deliberately out of scope; format is preserved, not transformed.
- **Privacy:** the default `google` engine sends text to Google's public endpoint (off-device).
  For confidential documents use `-e nllb` (offline NMT) or a self-hosted `-e libretranslate`. See
  [docs/CONFIGURATION.md](docs/CONFIGURATION.md#environment-variables).

---

## License

**GNU AGPL-3.0** — free and open source. © 2026 Muhammad Mishbakhuz Zuhail.

You may use, study, modify, and redistribute this software under the terms of the
[GNU Affero General Public License v3.0](LICENSE). The AGPL is **strong copyleft**: any modified
version — including one you run as a network/web service — must also be released under the AGPL with
its source and **must keep the original copyright and attribution**. It cannot be taken closed or
re-claimed as someone else's work. Every source file carries an `SPDX-License-Identifier:
AGPL-3.0-only` header.

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) (DCO sign-off + CLA). Third-party
dependencies and model weights (PyMuPDF/AGPL, NLLB-200·Surya/CC-BY-NC, …) remain under their own
licenses.
