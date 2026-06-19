# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Echo translator — no-op passthrough that tags text so you can see the pipeline ran.

Used for testing extract->translate->regenerate end-to-end without any model or API.
"""

from __future__ import annotations

from ..config import Config


class EchoTranslator:
    name = "echo"
    cacheable = False        # never write "[id] ..." placeholders to the persistent TM
    is_noop = True           # no-op engine: skip text-aware passes (auto-glossary, residual, align)

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        tgt = cfg.target_lang or "??"
        return [f"[{tgt}] {t}" for t in texts]
