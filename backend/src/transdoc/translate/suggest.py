# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Review suggestion engine: in-context word/phrase SYNONYMS and sentence REPHRASINGS over the
translated text, for the CAT-style review UI (a Grammarly/DeepL-Write-like assist layer, not a
full editor). Backed by a small local instruct LLM (Qwen2.5-3B-Instruct by default), loaded on
demand and released after use so it doesn't stack with the extract/QE models on a small box.

Optional: needs the [suggest] extra (transformers + torch, 4-bit via bitsandbytes when available).
Without it the API endpoints return 503 and the UI hides the feature — exactly like /alternatives.
"""

from __future__ import annotations

import json
import os
import threading

from ..config import Config


class SuggestError(RuntimeError):
    """Raised when the suggestion model is unavailable or returns nothing usable."""


# style/mode -> a directive woven into the rephrase prompt. PR-2 surfaces these as UI presets.
STYLE_DIRECTIVES = {
    "general": "clear, neutral and natural",
    "professional": "professional, polished and businesslike",
    "academic": "a formal academic register, precise and impersonal",
    "friendly": "warm, casual and approachable",
    "concise": "as concise as possible without losing meaning",
}
DEFAULT_STYLE = "general"


class Suggester:
    """Lazy singleton around a local instruct LLM. Mirrors WordAligner/QualityEstimator: the model
    is class-cached and `release()`d after a review session so it never coexists with paddle/COMET."""

    _model = None
    _tok = None
    _ok = True
    _lock = threading.Lock()   # serialise the lazy load — endpoints run in the anyio threadpool
    MODEL = os.environ.get("SUGGEST_MODEL", "Qwen/Qwen2.5-3B-Instruct")

    @classmethod
    def available(cls) -> bool:
        import importlib.util
        return cls._ok and importlib.util.find_spec("transformers") is not None

    @classmethod
    def release(cls) -> None:
        """Drop the model + free its memory (peak-memory hygiene — see align.WordAligner.release)."""
        cls._model = None
        cls._tok = None
        cls._ok = True
        try:
            import gc
            gc.collect()
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _load(self):
        # Double-checked lock: two concurrent /api/synonyms calls must not each load a 3 GB model
        # (transient 2x in VRAM = the 6 GB OOM the box can't take) nor tear the _tok/_model writes.
        if Suggester._model is None and Suggester._ok:
            with Suggester._lock:
                if Suggester._model is None and Suggester._ok:
                    try:
                        import torch
                        from transformers import AutoModelForCausalLM, AutoTokenizer
                        kw: dict = {}
                        # 4-bit on GPU when bitsandbytes present (~2.5 GB on a 6 GB card); else fp16/CPU
                        import importlib.util
                        if torch.cuda.is_available() and importlib.util.find_spec("bitsandbytes"):
                            from transformers import BitsAndBytesConfig
                            kw["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True)
                            kw["device_map"] = "auto"
                        elif torch.cuda.is_available():
                            kw["torch_dtype"] = torch.float16
                            kw["device_map"] = "auto"
                        tok = AutoTokenizer.from_pretrained(self.MODEL)
                        model = AutoModelForCausalLM.from_pretrained(self.MODEL, **kw)
                        model.eval()
                        Suggester._tok, Suggester._model = tok, model   # publish together, last
                    except Exception:
                        Suggester._ok = False      # missing transformers / model / OOM
        return Suggester._model

    def _chat(self, system: str, user: str, *, max_new_tokens: int = 256,
              temperature: float = 0.7) -> str:
        model = self._load()
        if model is None:
            raise SuggestError("suggestion model unavailable")
        import torch
        tok = Suggester._tok
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = tok.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ids = tok(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new_tokens, do_sample=temperature > 0,
                                 temperature=max(temperature, 0.01), top_p=0.9,
                                 pad_token_id=tok.eos_token_id)
        return tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

    @staticmethod
    def _parse_list(content: str, key: str) -> list[str]:
        """Pull a JSON {key: [...]} list out of the model's reply, tolerating code fences."""
        c = content.strip()
        if c.startswith("```"):
            # ```json\n{...}``` -> drop the fence + optional language tag (removeprefix, NOT
            # lstrip("json") which would strip any leading j/s/o/n chars from real content).
            c = c.split("```")[1].removeprefix("json").strip()
        try:
            obj = json.loads(c)
        except Exception:
            start, end = c.find("["), c.rfind("]")
            if start == -1 or end == -1:
                raise SuggestError("model did not return a JSON list")
            obj = json.loads(c[start:end + 1])
        items = obj.get(key, obj) if isinstance(obj, dict) else obj
        if not isinstance(items, list):
            raise SuggestError(f"{key} not a list")
        seen, out = set(), []
        for it in items:
            s = str(it).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    def synonyms(self, phrase: str, context: str, cfg: Config, n: int = 6) -> list[str]:
        """In-context alternatives for ``phrase`` within the translated sentence ``context`` —
        meaning- and register-preserving, natural in the target language. Excludes the phrase itself."""
        if not phrase.strip():
            return []
        n = max(1, min(10, n))
        lang = cfg.target_lang
        system = (
            f"You help review a translation written in {lang}. Given a sentence and a selected "
            "phrase inside it, propose alternative wordings for ONLY that phrase that fit the "
            "sentence and read naturally. Each alternative must mean the SAME as the original phrase "
            "(true synonyms — never antonyms, opposites or unrelated words) and keep the same "
            "register. "
            f"CRITICAL: every alternative MUST be a real word/phrase written in {lang} (the same "
            "language as the input). Do NOT translate to any other language and do not invent "
            "non-words. Do not change numbers, names or punctuation. Exclude the original phrase. "
            f'Return ONLY JSON: {{"synonyms": ["...", "..."]}} with up to {n} distinct items in {lang}.'
        )
        user = json.dumps({"sentence": context or phrase, "phrase": phrase}, ensure_ascii=False)
        return [s for s in self._parse_list(self._chat(system, user, temperature=0.8), "synonyms")
                if s.strip().lower() != phrase.strip().lower()]

    def rephrase(self, sentence: str, cfg: Config, style: str = DEFAULT_STYLE,
                 n: int = 3) -> list[str]:
        """Rewrite ``sentence`` (already in the target language) in the requested style/mode."""
        if not sentence.strip():
            return []
        n = max(1, min(5, n))
        directive = STYLE_DIRECTIVES.get(style, STYLE_DIRECTIVES[DEFAULT_STYLE])
        lang = cfg.target_lang
        system = (
            f"You refine text written in {lang}. Rewrite the sentence to be {directive}. "
            f"CRITICAL: the rewrite MUST stay in {lang} (the same language as the input) — do NOT "
            "translate it to any other language. Keep the meaning, and preserve numbers, dates, IDs, "
            "URLs and proper nouns exactly. "
            f'Return ONLY JSON: {{"rephrasings": ["...", "..."]}} with {n} distinct rewrites in {lang}.'
        )
        user = json.dumps({"sentence": sentence, "style": style}, ensure_ascii=False)
        return self._parse_list(self._chat(system, user, temperature=0.7), "rephrasings")
