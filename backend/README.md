# transdoc backend

The Python package (`transdoc`): the document pipeline, CLI, and FastAPI API that the
`../frontend` talks to. Project overview is in the repo-root [`README.md`](../README.md); full
documentation is under [`../docs/`](../docs).

## Install & run

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,formats,api]"      # core + tests + extra formats + web API

python server.py                          # web UI + REST API → http://127.0.0.1:8000
transdoc translate input.pdf --lang id    # CLI, one-shot
pytest                                     # offline test suite (echo engine)
```

`python server.py` launches the web UI + REST API — a thin wrapper around the same app as
`transdoc serve`. It needs the `api` extra (FastAPI + uvicorn), installed above. API docs are at
`/docs`; rebind with `python server.py 0.0.0.0 8080` (or `TRANSDOC_HOST`/`TRANSDOC_PORT`).

## Where to look next

| Topic | Document |
|-------|----------|
| Running the tool (CLI/API/formats) | [../docs/USAGE.md](../docs/USAGE.md) |
| Config fields, engines, env vars | [../docs/CONFIGURATION.md](../docs/CONFIGURATION.md) |
| Quality pipeline | [../docs/QUALITY.md](../docs/QUALITY.md) |
| Dev setup, tests, eval, paddle venv, code layout | [../docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md) |

## Structure (summary)

```
server.py        launcher for the web UI + REST API (== `transdoc serve`)
src/transdoc/    cli · config · pipeline · ir · ingest · extract · ocr · diagnose
                 · translate · regenerate · layout · api · eval
tests/           pytest (offline)
scripts/         dev/QA utilities (fetch_corpus, make_samples, bench_*, qa_fidelity, …)
corpus/          local test documents (git-ignored)
```

Full code-layout breakdown: [../docs/DEVELOPMENT.md](../docs/DEVELOPMENT.md#code-layout).
