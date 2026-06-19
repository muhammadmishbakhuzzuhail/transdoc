# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""EasyOCR engine — multilingual neural OCR (80+ languages, box + confidence).

The strong escalation engine for the script router: where Tesseract collapses on a non-Latin
scan (Devanagari/Arabic/CJK/...), EasyOCR recognizes it with per-line boxes and confidence, so
the result drops straight into the IR like any other OCR output. Torch-based (no paddlepaddle, so
no venv clash); GPU is used automatically when a CUDA torch build is installed, else CPU.

Boxes are pixel coordinates of the SAME image the router hands every engine, so they share the
Tesseract coordinate space (the renderer rescales ocr-sourced blocks uniformly).
"""

from __future__ import annotations

import io

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence

# Detected script (Tesseract OSD names) -> EasyOCR language codes. English is co-loaded because
# it is compatible with every reader and most docs carry some Latin (numbers, names, units).
_SCRIPT_LANGS = {
    "Latin": ["en"], "Cyrillic": ["ru"], "Greek": ["en"], "Arabic": ["ar"],
    "Hebrew": ["en"], "Devanagari": ["hi"], "Bengali": ["bn"], "Tamil": ["ta"],
    "Telugu": ["te"], "Kannada": ["kn"], "Thai": ["th"], "Han": ["ch_sim"],
    "Hangul": ["ko"], "Japanese": ["ja"],
}
# Explicit source ISO 639-1 -> EasyOCR codes (some differ: zh -> ch_sim).
_ISO_LANGS = {
    "zh": "ch_sim", "zh-cn": "ch_sim", "zh-tw": "ch_tra", "ja": "ja", "ko": "ko",
    "ar": "ar", "hi": "hi", "bn": "bn", "ta": "ta", "te": "te", "kn": "kn",
    "th": "th", "ru": "ru",
}


def _poly_to_bbox(poly) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def parse_results(results, page: int = 0) -> list[Block]:
    """EasyOCR readtext output [(poly, text, conf), ...] -> IR Blocks (pixel bbox + ocr conf)."""
    out: list[Block] = []
    for i, item in enumerate(results):
        try:
            poly, text, conf = item
        except Exception:
            continue
        if not (text or "").strip():
            continue
        x0, y0, x1, y1 = _poly_to_bbox(poly)
        out.append(Block(
            id=f"p{page}-e{i}", type=BlockType.PARAGRAPH, page=page,
            bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), text=text.strip(),
            confidence=Confidence(source="ocr", ocr=float(conf))))
    return out


class EasyOCREngine:
    name = "easyocr"
    _readers: dict = {}          # langs-tuple -> easyocr.Reader (process-wide cache)

    def _langs(self, cfg: Config, script: str | None) -> list[str]:
        if cfg.source_lang and cfg.source_lang != "auto":
            code = _ISO_LANGS.get(cfg.source_lang.lower(), cfg.source_lang.lower())
            return [code] if code == "en" else [code, "en"]
        langs = _SCRIPT_LANGS.get(script or "Latin", ["en"])
        return langs if langs == ["en"] else [*langs, "en"]

    def _use_gpu(self) -> bool:
        # EasyOCR's detector conv peaks past ~5 GB on a full-page scan, so it OOMs (and CUDA
        # segfaults, uncatchable) on small cards like a 6 GB laptop GPU. Default to CPU (stable,
        # only ~1s slower per page) and let a roomy GPU opt in with TRANSDOC_EASYOCR_GPU=1.
        import os
        if os.environ.get("TRANSDOC_EASYOCR_GPU") != "1":
            return False
        try:
            import torch
            return torch.cuda.is_available()
        except Exception:
            return False

    def _reader(self, langs: list[str]):
        import easyocr
        key = tuple(langs)
        if key not in EasyOCREngine._readers:
            EasyOCREngine._readers[key] = easyocr.Reader(
                langs, gpu=self._use_gpu(), verbose=False)
        return EasyOCREngine._readers[key]

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        import numpy as np
        from PIL import Image

        from .router import detect_script
        script = None
        if not cfg.source_lang or cfg.source_lang == "auto":
            script = detect_script(img)
        reader = self._reader(self._langs(cfg, script))
        arr = np.array(Image.open(io.BytesIO(img)).convert("RGB"))
        results = reader.readtext(arr, detail=1, paragraph=False)
        return parse_results(results, page)
