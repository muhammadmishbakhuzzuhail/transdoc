# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""NLLB-200 translator — offline neural MT, 200 languages.

LICENSE: NLLB-200 weights are CC-BY-NC-4.0 (non-commercial, "not for production").
Do not ship in a commercial product; use ARGOS for that. Lazy-loaded (pulls torch).
"""

from __future__ import annotations

from ..config import Config

# Minimal ISO 639-1 -> NLLB FLORES-200 code map for common targets. Extend as needed.
NLLB_CODE = {
    "en": "eng_Latn", "id": "ind_Latn", "ar": "arb_Arab", "zh": "zho_Hans",
    "ja": "jpn_Jpan", "ko": "kor_Hang", "ru": "rus_Cyrl", "hi": "hin_Deva",
    "th": "tha_Thai", "vi": "vie_Latn", "de": "deu_Latn", "fr": "fra_Latn",
    "es": "spa_Latn", "pt": "por_Latn", "it": "ita_Latn", "nl": "nld_Latn",
}


class NLLBTranslator:
    name = "nllb"
    _model = None
    _tok = None

    def __init__(self, model: str | None = None):
        if NLLBTranslator._model is None:
            import os

            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            # quality knob: distilled-600M (fast) | distilled-1.3B | 3.3B (best, ~6GB).
            # Precedence: NLLB_MODEL env var > cfg.nllb_model (passed in) > default.
            name = os.environ.get("NLLB_MODEL") or model or "facebook/nllb-200-distilled-600M"
            NLLBTranslator._tok = AutoTokenizer.from_pretrained(name)
            kwargs = {}
            if torch.cuda.is_available():
                kwargs = {"torch_dtype": torch.float16}
            NLLBTranslator._model = AutoModelForSeq2SeqLM.from_pretrained(name, **kwargs)
            if torch.cuda.is_available():
                NLLBTranslator._model = NLLBTranslator._model.to("cuda")

    def _code(self, lang: str | None, default: str) -> str:
        if not lang or lang == "auto":
            return default
        return NLLB_CODE.get(lang, default)

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        import torch

        tok, model = NLLBTranslator._tok, NLLBTranslator._model
        src_code = self._code(src, "eng_Latn")
        tgt_code = self._code(cfg.target_lang, "eng_Latn")
        tok.src_lang = src_code
        bos = tok.convert_tokens_to_ids(tgt_code)

        out: list[str] = []
        CHUNK = 16
        for i in range(0, len(texts), CHUNK):
            batch = texts[i:i + CHUNK]
            enc = tok(batch, return_tensors="pt", padding=True, truncation=True,
                      max_length=512)
            enc = {k: v.to(model.device) for k, v in enc.items()}
            with torch.no_grad():
                gen = model.generate(
                    **enc, forced_bos_token_id=bos, max_length=512,
                    num_beams=4,                 # beam search -> higher quality than greedy
                    no_repeat_ngram_size=3,      # suppress repetition loops
                    length_penalty=1.0,
                )
            out.extend(tok.batch_decode(gen, skip_special_tokens=True))
        return out
