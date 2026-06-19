# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Surya OCR 2 — default GPU engine (0.65B VLM, 91 langs, layout + reading order).

Lazy-loaded: importing surya pulls torch, so we only touch it when this engine is
actually selected. Models are cached after first load. Falls back is the caller's job.
"""

from __future__ import annotations

import io

from ..config import Config
from ..ir import BBox, Block, BlockType, Confidence


class SuryaOCR:
    name = "surya"
    _predictors = None  # cached (recognition, detection)

    def _load(self):
        if SuryaOCR._predictors is None:
            from surya.detection import DetectionPredictor
            from surya.recognition import RecognitionPredictor

            SuryaOCR._predictors = (RecognitionPredictor(), DetectionPredictor())
        return SuryaOCR._predictors

    def recognize_image_bytes(self, img: bytes, cfg: Config, page: int = 0) -> list[Block]:
        from PIL import Image

        rec, det = self._load()
        image = Image.open(io.BytesIO(img)).convert("RGB")
        # Surya autodetects script/lang; no lang list needed in recent versions.
        preds = rec([image], det_predictor=det)
        result = preds[0]

        blocks: list[Block] = []
        for idx, line in enumerate(getattr(result, "text_lines", [])):
            text = (line.text or "").strip()
            if not text:
                continue
            bb = line.bbox  # [x0, y0, x1, y1]
            conf = float(getattr(line, "confidence", 1.0) or 1.0)
            blk = Block(
                id=f"p{page}-surya{idx}",
                type=BlockType.PARAGRAPH,
                page=page,
                text=text,
                bbox=BBox(x0=bb[0], y0=bb[1], x1=bb[2], y1=bb[3]),
                confidence=Confidence(source="ocr", ocr=round(conf, 3)),
            )
            if conf < cfg.flag_threshold:
                blk.flags["low_ocr_confidence"] = f"{conf:.0%}"
            blocks.append(blk)
        return blocks
