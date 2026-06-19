# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""EPUB extraction via ebooklib + BeautifulSoup.

EPUB is a zip of XHTML documents. We walk every text node (skipping script/style) in document
order and emit one IR block per non-empty node, id = ``{item_id}#{n}`` where n is the node's
ordinal within that document. The renderer re-walks identically and swaps the text node's
string, preserving all markup, CSS, images, and the spine.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Confidence, Document
from .base import reflow_order

_SKIP_PARENTS = {"script", "style", "title"}


def iter_text_nodes(soup):
    """Yield (ordinal, NavigableString) for translatable text nodes, in document order."""
    from bs4 import (
        CData, Comment, Declaration, Doctype, NavigableString, ProcessingInstruction,
    )

    # Comment/Declaration/Doctype/PI/CData are NavigableString *subclasses* — the XML decl
    # (<?xml ...?>) and <!DOCTYPE html> would otherwise leak in as translatable "text".
    special = (CData, Comment, Declaration, Doctype, ProcessingInstruction)

    n = 0
    for node in soup.find_all(string=True):
        if not isinstance(node, NavigableString) or isinstance(node, special):
            continue
        parent = node.parent.name if node.parent else ""
        if parent in _SKIP_PARENTS:
            continue
        if node.strip():
            yield n, node
            n += 1


def extract(path: str, cfg: Config) -> Document:
    from bs4 import BeautifulSoup
    from ebooklib import ITEM_DOCUMENT, epub

    try:
        book = epub.read_epub(path)
    except Exception as e:
        raise ValueError(f"unreadable or corrupt EPUB: {e}") from e
    out = Document(source_path=path, mime="application/epub+zip")
    page = 0
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        for n, node in iter_text_nodes(soup):
            out.blocks.append(Block(
                id=f"{item.get_id()}#{n}", type=BlockType.PARAGRAPH, page=page,
                text=str(node), confidence=Confidence(source="digital")))
        page += 1
    reflow_order(out)
    return out
