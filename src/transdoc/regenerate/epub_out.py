"""EPUB renderer — round-trip. Reopen the book, re-walk each XHTML document identically to
the extractor, replace each translated text node in place, and write the book back out —
markup, CSS, images, and spine order preserved."""

from __future__ import annotations

from ..config import Config
from ..extract.epub import iter_text_nodes
from ..ir import Document


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from bs4 import BeautifulSoup, NavigableString
    from ebooklib import ITEM_DOCUMENT, epub

    m = {b.id: b.output_text for b in doc.blocks}
    book = epub.read_epub(doc.source_path)
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        changed = False
        for n, node in iter_text_nodes(soup):
            t = m.get(f"{item.get_id()}#{n}")
            if t is not None:
                node.replace_with(NavigableString(t))
                changed = True
        if changed:
            item.set_content(str(soup).encode("utf-8"))
    epub.write_epub(out_path, book)
    return out_path
