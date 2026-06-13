"""PaddleOCR (PP-OCRv5/v6) engine — lightweight det+rec, opt-in.

Benchmarked far stronger than Tesseract on degraded and non-Latin scans (Devanagari 0.95 vs
0.29, Fraktur 0.98 vs 0.67, Cyrillic 0.76 vs 0.31 — see docs/RESEARCH.md), while the models
are small enough to run CPU-only. The 0.9B PaddleOCR-VL was rejected (OOM on 6 GB GPU /
11 GB RAM); this is the classic pipeline, not the VL.

Install: ``pip install -e ".[paddleocr]"`` (pulls paddlepaddle + paddleocr). Select with
``--ocr paddle``. Pass ``--source <iso>`` for the right per-language model.
"""

from __future__ import annotations

import io

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Style

# transdoc ISO codes -> PaddleOCR language codes (most pass through; these differ).
PADDLE_LANG = {
    "de": "german", "ja": "japan", "ko": "korean",
    "zh": "ch", "zh-hans": "ch", "zh-cn": "ch",
    "zh-hant": "chinese_cht", "zh-tw": "chinese_cht",
}

# Tesseract OSD script name -> a representative PaddleOCR language model. Lets us pick the
# right model for a scan when --source is "auto", since the script can be read off the image
# (via Tesseract OSD) without first knowing the language. Refined within Latin by a text
# language-detect pass after the first OCR.
SCRIPT_TO_LANG = {
    "Latin": "en", "Cyrillic": "ru", "Greek": "el", "Devanagari": "hi",
    "Arabic": "ar", "Hebrew": "he", "Han": "ch", "HanS": "ch", "HanT": "chinese_cht",
    "Japanese": "japan", "Hangul": "korean", "Korean": "korean", "Thai": "th",
    "Bengali": "bn", "Tamil": "ta", "Telugu": "te",
}


# OSD script confidence below this is noise — a clean script reads high (e.g. Devanagari
# ~45), false positives read ~0.1. Below the gate we return None and fall back to English
# (which is the right model for Latin scripts anyway, so only false non-Latin hits are risky).
_OSD_MIN_CONF = 1.5


def detect_script_lang(img: bytes) -> str | None:
    """Read the dominant script off the image with Tesseract OSD and map it to a PaddleOCR
    language. Returns None if OSD is unavailable or its confidence is too low."""
    try:
        import io

        import pytesseract
        from PIL import Image

        osd = pytesseract.image_to_osd(
            Image.open(io.BytesIO(img)), output_type=pytesseract.Output.DICT)
        if float(osd.get("script_conf", 0)) < _OSD_MIN_CONF:
            return None
        return SCRIPT_TO_LANG.get(osd.get("script"))
    except Exception:
        return None


class PaddleOCREngine:
    name = "paddle"

    def __init__(self):
        self._cache: dict[str, object] = {}   # lang -> PaddleOCR (heavy init, reuse per lang)

    def _lang(self, cfg: Config, img: bytes | None = None) -> str:
        src = (cfg.source_lang or "auto").lower()
        if src == "auto":
            # no source given -> read the script off the image, fall back to English
            return (detect_script_lang(img) if img else None) or "en"
        return PADDLE_LANG.get(src, src)

    def _engine(self, lang: str):
        if lang not in self._cache:
            from paddleocr import PaddleOCR
            try:
                self._cache[lang] = PaddleOCR(
                    lang=lang, use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False)
            except Exception:
                # unknown language model -> fall back to English so we still produce output
                self._cache[lang] = PaddleOCR(
                    lang="en", use_doc_orientation_classify=False,
                    use_doc_unwarping=False, use_textline_orientation=False)
        return self._cache[lang]

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        import numpy as np
        from PIL import Image

        arr = np.array(Image.open(io.BytesIO(img)).convert("RGB"))
        result = self._engine(self._lang(cfg, img)).predict(arr)

        blocks: list[Block] = []
        idx = 0
        for r in result:
            texts = r["rec_texts"]
            scores = r["rec_scores"]
            polys = r["rec_polys"]            # each = quad of (x, y) in image pixels
            for text, score, poly in zip(texts, scores, polys):
                text = (text or "").strip()
                if not text:
                    continue
                xs = [float(p[0]) for p in poly]
                ys = [float(p[1]) for p in poly]
                conf = round(float(score), 3)
                blk = Block(
                    id=f"p{page}-pocr{idx}",
                    type=BlockType.PARAGRAPH,
                    page=page,
                    text=text,
                    bbox=BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys)),
                    style=Style(),
                    confidence=Confidence(source="ocr", ocr=conf),
                )
                if conf < cfg.flag_threshold:
                    blk.flags["low_ocr_confidence"] = f"{conf:.0%}"
                blocks.append(blk)
                idx += 1
        return blocks
