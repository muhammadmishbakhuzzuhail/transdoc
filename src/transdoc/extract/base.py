"""Extractor protocol + shared helpers. Each extractor produces an IR Document."""

from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..ir import Block, Document


class Extractor(Protocol):
    def extract(self, path: str, cfg: Config) -> Document: ...


def block_id(page: int, idx: int) -> str:
    return f"p{page}-b{idx}"


def reflow_order(doc: Document) -> None:
    """Assign a global reading_order from (page, existing order) if unset."""
    for i, b in enumerate(doc.ordered_blocks()):
        b.reading_order = i


def merge_block(blocks: list[Block]) -> str:
    return "\n\n".join(b.text for b in blocks if b.text.strip())
