"""Translator interface + shared logic that every engine reuses.

The translate phase walks the IR: translatable blocks get their text translated (and table
cells), verbatim blocks are left untouched, and the glossary is enforced uniformly so one
source term maps to one target rendering everywhere.
"""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..ir import Block, Document


class Translator(Protocol):
    name: str

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        """Translate a list of strings. Order preserved, 1:1 with input."""
        ...


def _apply_glossary(text: str, glossary: dict[str, str]) -> str:
    """Enforce term consistency. Longest terms first to avoid partial overlaps."""
    for term in sorted(glossary, key=len, reverse=True):
        if term and term in text:
            text = text.replace(term, glossary[term])
    return text


def translate_document(doc: Document, tr: Translator, cfg: Config) -> None:
    """Translate the whole IR in place. Collects translatable strings, batches them,
    writes results back to blocks and table cells, then enforces the glossary."""
    target = cfg.require_target()
    glossary = dict(cfg.glossary)

    # 1) collect (block paragraphs + table cells)
    items: list[tuple[str, object]] = []  # (text, sink)
    for b in doc.blocks:
        if b.type.value == "table" and b.table:
            for row in b.table.rows:
                for cell in row:
                    if cell.text.strip():
                        items.append((cell.text, cell))
        elif b.is_translatable:
            items.append((b.text, b))

    if not items:
        return

    texts = [t for t, _ in items]
    out = tr.translate_batch(texts, cfg, src=doc.source_lang)

    # 2) write back + glossary enforcement
    for (src_text, sink), translated in zip(items, out):
        translated = _apply_glossary(translated, glossary)
        if isinstance(sink, Block):
            sink.translated = translated
            sink.confidence.translation = sink.confidence.translation or 0.9
        else:  # Cell
            sink.translated = translated

    doc.target_lang = target
