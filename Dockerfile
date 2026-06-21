# transdoc — single-image build: FastAPI serves the built React UI + REST API on one port.
# Build context is the repo root:   docker build -t transdoc .
# Run:                              docker run --rm -p 8000:8000 transdoc   -> http://localhost:8000
#
# Bundles Tesseract (OCR) + LibreOffice (office<->PDF, legacy .doc/.rtf). The structured layout
# path (PaddleOCR PP-StructureV3, ~1.9 GB) is NOT in the base image — the pipeline falls back to
# the heuristic extractor automatically when paddle is absent. Default engine is the Google web
# endpoint, so a running container needs outbound network for translation.

# ---- stage 1: build the React frontend ----
FROM node:20-slim AS web
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build                       # -> /fe/dist (relative API base => same-origin)

# ---- stage 2: python runtime ----
FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSDOC_HOST=0.0.0.0 \
    TRANSDOC_PORT=8000

# OCR (tesseract + OSD + a common language set), office<->PDF (LibreOffice core apps),
# libmagic for python-magic, Noto fonts for LibreOffice rendering of non-Latin scripts.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-osd \
        tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
        tesseract-ocr-ita tesseract-ocr-por tesseract-ocr-nld \
        tesseract-ocr-chi-sim tesseract-ocr-jpn tesseract-ocr-kor \
        tesseract-ocr-ara tesseract-ocr-hin tesseract-ocr-rus \
        libreoffice-writer libreoffice-calc libreoffice-impress \
        libmagic1 fonts-noto-core fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/ ./backend/
RUN pip install "./backend[api,formats]"

# Bundle the built SPA so FastAPI serves it at / (and /assets via the StaticFiles mount).
COPY --from=web /fe/dist/ ./backend/src/transdoc/api/spa/

EXPOSE 8000
WORKDIR /app/backend
CMD ["python", "server.py"]
