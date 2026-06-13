# transdoc web UI

React (Vite + TypeScript + Tailwind + shadcn-style) frontend for the transdoc FastAPI backend.
Frontend and backend run separately.

## Run

```bash
# 1. backend (repo root) — the REST API on :8000
transdoc serve

# 2. frontend (this dir)
npm install
npm run dev            # http://localhost:5173  (proxies /api -> :8000)
```

For a production build set the backend origin and build static assets:

```bash
VITE_API_BASE=https://api.example.com npm run build   # -> dist/
```

The backend's `TRANSDOC_CORS_ORIGINS` must include the frontend origin.

## What it shows

Core: upload, source/target language, output format, engine, fidelity, **layout model**
(`paddle` = crop figures/math/tables verbatim), OCR engine, register, page range, and the
bilingual / quality / localize switches.

After a job completes it renders the full **analysis**: document profile, flagged items,
glossary resolution, reconstruction notes, plus region-crop / illegible / repair counts — and
download buttons for the translated file and the report.
