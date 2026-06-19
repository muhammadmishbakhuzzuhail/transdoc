# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Opus-MT / Marian translator — MIT-licensed, commercial-safe, no API key.

Helsinki-NLP per-pair models (e.g. Helsinki-NLP/opus-mt-en-id). Tiny, fast on CPU, ideal
for free deployment. Models auto-download per pair on first use and are cached.

Best for high-resource pairs (en<->id, en<->zh, ...). For pairs without a direct model,
falls back to pivoting through English when possible.
"""

from __future__ import annotations

from ..config import Config

_PIVOT = "en"


class OpusMTTranslator:
    name = "opusmt"
    _cache: dict[str, object] = {}

    def __init__(self):
        import transformers  # noqa: F401  (ensure available early)

    def _model(self, src: str, tgt: str):
        key = f"{src}-{tgt}"
        if key in OpusMTTranslator._cache:
            return OpusMTTranslator._cache[key]
        import torch
        from transformers import MarianMTModel, MarianTokenizer

        name = f"Helsinki-NLP/opus-mt-{src}-{tgt}"
        tok = MarianTokenizer.from_pretrained(name)
        model = MarianMTModel.from_pretrained(name)
        if torch.cuda.is_available():
            model = model.to("cuda")
        OpusMTTranslator._cache[key] = (tok, model)
        return tok, model

    def _translate_pair(self, texts: list[str], src: str, tgt: str) -> list[str]:
        import torch

        tok, model = self._model(src, tgt)
        out: list[str] = []
        CHUNK = 16
        for i in range(0, len(texts), CHUNK):
            batch = texts[i:i + CHUNK]
            enc = tok(batch, return_tensors="pt", padding=True, truncation=True,
                      max_length=512)
            enc = {k: v.to(model.device) for k, v in enc.items()}
            with torch.no_grad():
                gen = model.generate(**enc, max_length=512)
            out.extend(tok.batch_decode(gen, skip_special_tokens=True))
        return out

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        s = (src if src and src != "auto" else _PIVOT)
        t = cfg.target_lang or _PIVOT
        if s == t:
            return list(texts)
        try:
            return self._translate_pair(texts, s, t)
        except Exception:
            # pivot through English: s->en->t
            try:
                mid = texts if s == _PIVOT else self._translate_pair(texts, s, _PIVOT)
                return mid if t == _PIVOT else self._translate_pair(mid, _PIVOT, t)
            except Exception:
                return list(texts)  # never drop content
