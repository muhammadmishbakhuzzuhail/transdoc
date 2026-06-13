# transdoc backend

The Python package (`transdoc`): the document pipeline, CLI, and FastAPI API that the
`../frontend` talks to. Project overview is in the repo-root `README.md`.

## Install & run

```bash
cd backend
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,formats]"          # core + tests + extra formats

transdoc translate input.pdf --lang id --to pdf      # CLI
transdoc serve                                        # REST API on :8000
pytest                                                # offline test suite (echo engine)
```

## Layout (`--layout paddle`)

Region detection (PP-DocLayout) crops figures/math/tables verbatim. paddlepaddle and torch
can't share a venv, so it runs out-of-process: create an isolated paddle venv and point
`TRANSDOC_LAYOUT_PYTHON` at its python (default search: `./layout_venv/bin/python`).

```bash
python3.11 -m venv layout_venv
layout_venv/bin/pip install -e . "paddlepaddle-gpu==3.3.1" "paddleocr>=3.0"
transdoc translate paper.pdf --lang id --to pdf --layout paddle
```

## Structure

```
src/transdoc/
  cli.py config.py pipeline.py ir.py     entry, config, orchestrator, IR
  ingest/ extract/ ocr/ diagnose/ translate/ regenerate/   pipeline phases
  layout/        PP-DocLayout region detection (in-process or subprocess)
  api/           FastAPI app, async job store, analysis serializer
  assets/ headers.py limits.py report.py
tests/           pytest (offline)
scripts/         dev/QA utilities (qa_fidelity, bench_quality, fetch_corpus, …)
corpus/          test documents
```
