# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""MADLAD-400 translator — Apache-2.0, commercial-safe, no API key.

Google's T5-based multilingual MT covering 450+ languages in a single model. Target language
is selected with a leading "<2xx>" token; the source language is auto-detected, so this is a
true any->any engine — the right core for DeepL-style universal coverage in a commercial app.

Smallest official model is 3B (google/madlad400-3b-mt). On a 6GB GPU use 8-bit (bitsandbytes)
or fp16; falls back to CPU otherwise. For production, convert to CTranslate2 int8 for speed.
Lazy-loaded (pulls torch/transformers).
"""

from __future__ import annotations

import os

from ..config import Config


class MadladTranslator:
    name = "madlad"
    _model = None
    _tok = None

    def __init__(self):
        if MadladTranslator._model is None:
            import torch
            from transformers import AutoTokenizer, T5ForConditionalGeneration

            name = os.environ.get("MADLAD_MODEL", "google/madlad400-3b-mt")
            MadladTranslator._tok = AutoTokenizer.from_pretrained(name)
            kwargs = {}
            if torch.cuda.is_available():
                # try 8-bit to fit 3B on 6GB; fall back to fp16
                try:
                    import bitsandbytes  # noqa: F401

                    kwargs = {"load_in_8bit": True, "device_map": "auto"}
                except Exception:
                    kwargs = {"torch_dtype": torch.float16, "device_map": "auto"}
            model = T5ForConditionalGeneration.from_pretrained(name, **kwargs)
            MadladTranslator._model = model

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        import torch

        tok, model = MadladTranslator._tok, MadladTranslator._model
        tgt = cfg.target_lang or "en"
        prompts = [f"<2{tgt}> {t}" for t in texts]

        out: list[str] = []
        CHUNK = 8
        for i in range(0, len(prompts), CHUNK):
            batch = prompts[i:i + CHUNK]
            enc = tok(batch, return_tensors="pt", padding=True, truncation=True,
                      max_length=512)
            enc = {k: v.to(model.device) for k, v in enc.items()}
            with torch.no_grad():
                gen = model.generate(**enc, max_length=512)
            out.extend(tok.batch_decode(gen, skip_special_tokens=True))
        return out
