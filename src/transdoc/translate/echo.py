"""Echo translator — no-op passthrough that tags text so you can see the pipeline ran.

Used for testing extract->translate->regenerate end-to-end without any model or API.
"""

from __future__ import annotations

from ..config import Config


class EchoTranslator:
    name = "echo"

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        tgt = cfg.target_lang or "??"
        return [f"[{tgt}] {t}" for t in texts]
