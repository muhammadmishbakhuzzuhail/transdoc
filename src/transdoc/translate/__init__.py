"""Translator factory."""

from __future__ import annotations

from ..config import Config, Engine
from .base import Translator, translate_document  # noqa: F401


def get_translator(cfg: Config) -> Translator:
    if cfg.engine == Engine.ECHO:
        from .echo import EchoTranslator

        return EchoTranslator()
    if cfg.engine == Engine.OPENROUTER:
        from .openrouter import OpenRouterTranslator

        return OpenRouterTranslator()
    if cfg.engine == Engine.ANTHROPIC:
        from .anthropic import AnthropicTranslator

        return AnthropicTranslator()
    if cfg.engine == Engine.NLLB:
        from .nllb import NLLBTranslator

        return NLLBTranslator()
    if cfg.engine == Engine.OPUSMT:
        from .opusmt import OpusMTTranslator

        return OpusMTTranslator()
    if cfg.engine == Engine.ARGOS:
        from .argos import ArgosTranslator

        return ArgosTranslator()
    raise ValueError(f"unknown engine: {cfg.engine}")
