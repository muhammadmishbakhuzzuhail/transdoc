# Development

Setting up a dev environment, running tests and lint, the evaluation harness, and the code layout.
For *using* the tool see [USAGE.md](USAGE.md).

> **Scope:** contributing to and testing transdoc. End-user run instructions live in the root
> `README.md` and [USAGE.md](USAGE.md).

---

## Setup

From the repo root (`make` wraps the steps; targets create `backend/.venv`):

```bash
make setup            # backend .venv (pip install -e ".[dev,formats,api]") + frontend npm ci
make setup-backend    # backend only
make setup-frontend   # frontend only
make setup-layout     # optional isolated paddle venv for PP-StructureV3 (see below)
```

Manual backend setup:

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,formats,api]"
```

### Optional dependency extras

The package defines fine-grained extras (`pyproject.toml`). Install only what you need:

| Extra | Pulls in |
|-------|----------|
| `dev` | pytest, ruff, httpx (test client) |
| `formats` | pptx / xlsx / epub / subtitles round-trip |
| `api` | FastAPI + uvicorn (needed for `serve` / `server.py`) |
| `detect` | lingua language detection (more accurate, ~1.2 GB RAM) |
| `qe` | COMET-Kiwi quality estimation |
| `align` | word-alignment style transfer |
| `nmt` | offline NMT (MADLAD / Opus-MT / NLLB) |
| `indic` | IndicTrans2 |
| `llm` | OpenRouter / Anthropic engines |
| `surya` / `easyocr` / `paddleocr` | extra OCR backends |
| `pdf` / `quant` / `scale` / `argos` | misc backends |

---

## Tests & lint

```bash
cd backend
pytest                 # offline suite — uses the `echo` engine, no network, no GPU
ruff check .           # lint
```

Or from the root: `make test`, `make lint`.

The test suite is offline and deterministic. It does **not** hit translation engines, GPUs, Ollama,
or paddle — those paths are stubbed. Do not run two heavy suites concurrently (torch + COMET ×2 can
exhaust RAM).

---

## Evaluation harness

Quality is measured, not asserted. The harness scores structure/fidelity/CER/WER/chrF and gates
against a committed baseline.

```bash
cd backend
python -m transdoc.eval.harness src/transdoc/eval/samples --engine echo
make eval              # full eval; see the Makefile for per-metric targets (eval-translate,
                       # eval-ocr, eval-table, eval-reading-order, eval-layout, quality-gate, …)
```

- **Committed fixtures:** `src/transdoc/eval/samples/digital_two_page.pdf` and `digital_table.docx`
  are deterministic samples anchored by `eval/baseline.json` (the regression gate). Regenerate with
  `python -m transdoc.eval.fixtures src/transdoc/eval/samples`. They are committed on purpose — the
  baseline expects these exact files.
- **Test corpus (local only, git-ignored):** `backend/corpus/` holds ~50 real + synthetic documents
  for broader evaluation. They are reproducible — fetch with `scripts/fetch_corpus.sh` and generate
  synthetics with `scripts/make_samples.py` — so they are not committed (`corpus/README.md` is the
  manifest).

---

## PP-StructureV3 / paddle (isolated venv)

paddlepaddle and torch can't share a venv, so the structured-extraction path runs **out of
process**. Create an isolated paddle venv and point `TRANSDOC_LAYOUT_PYTHON` at it:

```bash
make setup-layout       # creates backend/layout_venv with paddlepaddle + paddleocr
# or manually:
python3.11 -m venv backend/layout_venv
backend/layout_venv/bin/pip install -e backend "paddlepaddle-gpu==3.3.1" "paddleocr>=3.0"
```

Default search path is `./layout_venv/bin/python`. Disable the structured path entirely with
`TRANSDOC_LAYOUT_DISABLE=1`. On CPU, paddle requires `enable_mkldnn=False` (oneDNN is broken there);
this is already handled in code.

> **GPU note:** the reference machine has a 6 GB GPU shared with other work. Never stack two GPU
> models (e.g. COMET + Ollama + paddle) simultaneously — the pipeline releases models between phases
> for this reason.

---

## Code layout

```
backend/
  server.py            web UI + REST API launcher (== `transdoc serve`)
  src/transdoc/
    cli.py             Typer CLI (entry point)
    config.py          Config model + enums (Engine/OCREngine/Fidelity/…)
    pipeline.py        the orchestrator (stage sequence)
    ir.py              Intermediate Representation — the single canonical model
    ingest/            format detection, form detection
    extract/           per-format extractors (PDF/DOCX/ODT/…) → IR
    ocr/               script-routed multi-engine OCR + escalation
    diagnose/          document profiling
    translate/         engines, protector, TM, glossary, QE, align, residual, repair
    regenerate/        per-format renderers (IR → output)
    layout/            PP-StructureV3 structured extraction (in-process or subprocess)
    api/               FastAPI app, async job store, analysis serializer
    eval/              evaluation harness + committed fixtures + baseline.json
  tests/               pytest (offline)
  scripts/             dev/QA utilities (fetch_corpus, make_samples, bench_*, qa_fidelity, …)
  corpus/              local test documents (git-ignored)
frontend/              React UI (Vite + TypeScript + Tailwind + shadcn-style)
docs/                  design notes + this documentation set
```

The **IR** (`ir.py`) is the contract: every extractor writes it, every renderer reads it,
translation edits it in place. Swap any OCR/translation engine or output format without touching the
rest.

---

See also: [USAGE.md](USAGE.md) · [CONFIGURATION.md](CONFIGURATION.md) ·
[ARCHITECTURE.md](ARCHITECTURE.md) · [RESEARCH.md](RESEARCH.md) · [RISKS.md](RISKS.md)
