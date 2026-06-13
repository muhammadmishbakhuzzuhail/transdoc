"""Tesseract OCR — CPU fallback, always available.

Groups word-level boxes into line/paragraph blocks, carries OCR confidence so the QA
phase can flag low-confidence spans. Weak on Indic/complex scripts — prefer Surya there.
"""

from __future__ import annotations

import io

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence, Style
from .base import TESS_LANG


class TesseractOCR:
    name = "tesseract"

    def _langs(self, cfg: Config) -> str:
        import pytesseract

        avail = set(pytesseract.get_languages(config=""))
        wanted: list[str] = []
        if cfg.source_lang and cfg.source_lang != "auto":
            wanted.append(TESS_LANG.get(cfg.source_lang, cfg.source_lang))
        wanted.append("eng")
        # keep only installed, dedupe
        seen, out = set(), []
        for w in wanted:
            if w in avail and w not in seen:
                seen.add(w)
                out.append(w)
        return "+".join(out) or "eng"

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        import pytesseract
        from PIL import Image

        image = Image.open(io.BytesIO(img))
        lang = self._langs(cfg)
        data = pytesseract.image_to_data(image, lang=lang,
                                         output_type=pytesseract.Output.DICT)

        # Group words by (block_num, par_num, line_num) into paragraph blocks.
        paras: dict[tuple, dict] = {}
        n = len(data["text"])
        for i in range(n):
            txt = data["text"][i].strip()
            if not txt:
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i])
            x, y, w, h = (data["left"][i], data["top"][i],
                          data["width"][i], data["height"][i])
            p = paras.setdefault(key, {"words": [], "confs": [],
                                       "x0": 1e9, "y0": 1e9, "x1": 0, "y1": 0})
            p["words"].append(txt)
            p["confs"].append(conf / 100.0)
            p["x0"], p["y0"] = min(p["x0"], x), min(p["y0"], y)
            p["x1"], p["y1"] = max(p["x1"], x + w), max(p["y1"], y + h)

        blocks: list[Block] = []
        for idx, (key, p) in enumerate(sorted(paras.items())):
            text = " ".join(p["words"])
            avg_conf = sum(p["confs"]) / len(p["confs"])
            blk = Block(
                id=f"p{page}-ocr{idx}",
                type=BlockType.PARAGRAPH,
                page=page,
                text=text,
                bbox=BBox(x0=p["x0"], y0=p["y0"], x1=p["x1"], y1=p["y1"]),
                style=Style(),
                confidence=Confidence(source="ocr", ocr=round(avg_conf, 3)),
            )
            if avg_conf < cfg.flag_threshold:
                blk.flags["low_ocr_confidence"] = f"{avg_conf:.0%}"
            blocks.append(blk)
        return blocks
