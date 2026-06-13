"""OpenRouter LLM translator (default for real use).

Uses the OpenAI SDK pointed at OpenRouter, with model failover across the comma-separated
OPENROUTER_MODELS list (matching the existing backend's env contract). Document-level
context via batching + glossary enforcement in the system prompt.

Env:
  OPENROUTER_API_KEY   (required)
  OPENROUTER_MODELS    comma list, e.g. "deepseek/deepseek-chat,qwen/qwen-2.5-72b-instruct"
"""

from __future__ import annotations

import json
import os

from ..config import Config

DEFAULT_MODELS = [
    "deepseek/deepseek-chat",
    "qwen/qwen-2.5-72b-instruct",
    "google/gemma-3-27b-it",
    "meta-llama/llama-3.3-70b-instruct",
]


class OpenRouterTranslator:
    name = "openrouter"

    def __init__(self):
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        from openai import OpenAI

        self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)
        env_models = os.environ.get("OPENROUTER_MODELS", "")
        self.models = [m.strip() for m in env_models.split(",") if m.strip()] or DEFAULT_MODELS

    def _system(self, cfg: Config, src: str | None) -> str:
        gl = ""
        if cfg.glossary:
            pairs = "; ".join(f"{k} -> {v}" for k, v in cfg.glossary.items())
            gl = f"\nEnforce this glossary exactly: {pairs}."
        return (
            "You are a professional document translator. Translate each item of the input "
            f"JSON array from {src or 'the detected language'} to {cfg.target_lang}. "
            f"Domain: {cfg.domain}. Register: {cfg.register.value}. "
            "Translate meaning idiomatically. Preserve numbers, dates, IDs, codes, URLs, and "
            "proper nouns exactly. Keep inline placeholders/tags untouched. "
            "Return ONLY a JSON array of strings, same length and order as the input." + gl
        )

    def _call(self, system: str, payload: str) -> str:
        last = None
        for model in self.models:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": payload}],
                    temperature=0.2,
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:  # failover to next model
                last = e
                continue
        raise RuntimeError(f"all OpenRouter models failed: {last}")

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        out: list[str] = []
        CHUNK = 30
        system = self._system(cfg, src)
        for i in range(0, len(texts), CHUNK):
            batch = texts[i:i + CHUNK]
            text = self._call(system, json.dumps(batch, ensure_ascii=False))
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            try:
                parsed = json.loads(text)
                if len(parsed) != len(batch):
                    raise ValueError("length mismatch")
                out.extend(str(x) for x in parsed)
            except Exception:
                out.extend(batch)  # never drop content
        return out
