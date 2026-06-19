# transdoc backend

The Python package (`transdoc`): the document pipeline, CLI, and FastAPI API that the
`../frontend` talks to. Project overview is in the repo-root `README.md`.

## Install & run

```bash
cd backend
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,formats,api]"      # core + tests + extra formats + web API

python server.py                          # web UI + REST API → http://127.0.0.1:8000
transdoc translate input.pdf --lang id --to pdf      # CLI, one-shot
pytest                                                # offline test suite (echo engine)
```

`python server.py` launches the web UI + REST API (it's a thin wrapper around the same app —
`transdoc serve` is the equivalent CLI command). It needs the `api` extra (FastAPI + uvicorn),
installed above. API docs are at `http://127.0.0.1:8000/docs`; rebind with
`python server.py 0.0.0.0 8080` (or `TRANSDOC_HOST`/`TRANSDOC_PORT`). From the repo root,
`make serve` does the same thing.

## Layout (`--layout paddle`)

Structured extraction (PP-StructureV3) recovers layout regions, tables→HTML, formula→LaTeX and
reading order, cropping figures/math verbatim. paddlepaddle and torch can't share a venv, so it
runs out-of-process: create an isolated paddle venv and point `TRANSDOC_LAYOUT_PYTHON` at its
python (default search: `./layout_venv/bin/python`).

```bash
python3.11 -m venv layout_venv
layout_venv/bin/pip install -e . "paddlepaddle-gpu==3.3.1" "paddleocr>=3.0"
transdoc translate paper.pdf --lang id --to pdf --layout paddle
```

## Structure

```
server.py        launcher for the web UI + REST API (== `transdoc serve`)
src/transdoc/
  cli.py config.py pipeline.py ir.py     entry, config, orchestrator, IR
  ingest/ extract/ ocr/ diagnose/ translate/ regenerate/   pipeline phases
  layout/        PP-StructureV3 structured extraction (in-process or subprocess)
  api/           FastAPI app, async job store, analysis serializer
  assets/ headers.py limits.py report.py
tests/           pytest (offline)
scripts/         dev/QA utilities (qa_fidelity, bench_quality, fetch_corpus, …)
corpus/          test documents
```
