# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Anthropic LLM translator — default high-quality engine with document-level context
and glossary/terminology enforcement.

Sends a batch of segments as a numbered list and asks for a numbered list back, which
keeps alignment and lets the model use surrounding segments as context. Honors register,
domain, and the running glossary from the spec.
"""

from __future__ import annotations

import json
import os

from ..config import Config


class AnthropicTranslator:
    name = "anthropic"

    def __init__(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic

        self.client = Anthropic()

    def _system(self, cfg: Config, src: str | None) -> str:
        gl = ""
        if cfg.glossary:
            pairs = "; ".join(f"{k} -> {v}" for k, v in cfg.glossary.items())
            gl = f"\nEnforce this glossary exactly: {pairs}."
        return (
            "You are a professional document translator. Translate each numbered segment "
            f"from {src or 'the detected language'} to {cfg.target_lang}. "
            f"Domain: {cfg.domain}. Register: {cfg.register.value}. "
            "Translate meaning idiomatically, not word-for-word. Preserve numbers, dates, "
            "IDs, codes, URLs, and proper nouns exactly. Keep any inline placeholders/tags "
            "untouched. Return ONLY a JSON array of strings, same length and order as input."
            + gl
        )

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        out: list[str] = []
        # chunk to keep requests bounded
        CHUNK = 40
        for i in range(0, len(texts), CHUNK):
            batch = texts[i:i + CHUNK]
            payload = json.dumps(batch, ensure_ascii=False)
            msg = self.client.messages.create(
                model=cfg.anthropic_model,
                max_tokens=8192,
                system=self._system(cfg, src),
                messages=[{"role": "user", "content": payload}],
            )
            text = msg.content[0].text.strip()
            # strip code fences if present
            if text.startswith("```"):
                text = text.split("```")[1].lstrip("json").strip()
            try:
                parsed = json.loads(text)
                if len(parsed) != len(batch):
                    raise ValueError("length mismatch")
                out.extend(str(x) for x in parsed)
            except Exception:
                # fallback: keep source so nothing is dropped
                out.extend(batch)
        return out
