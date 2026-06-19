# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""EPUB renderer — round-trip. Reopen the book, re-walk each XHTML document identically to
the extractor, replace each translated text node in place, and write the book back out —
markup, CSS, images, and spine order preserved."""

from __future__ import annotations

from ..config import Config
from ..extract.epub import iter_text_nodes
from ..ir import Document


def _ensure_toc_uids(entries, prefix: str = "nav") -> None:
    """ebooklib drops navPoint ids when an epub is read then written: writing the NCX then
    fails with `item.uid == None`. Walk the (possibly nested) toc and backfill any missing
    uid so write_epub succeeds. Entries are EpubHtml/Link/Section, or (Section, [children])."""
    for idx, e in enumerate(entries):
        if isinstance(e, (tuple, list)):
            section, children = e[0], e[1]
            _ensure_toc_uids([section], f"{prefix}-{idx}")
            _ensure_toc_uids(children, f"{prefix}-{idx}")
            continue
        if not getattr(e, "uid", None):
            try:
                e.uid = getattr(e, "id", None) or f"{prefix}-{idx}"
            except Exception:
                pass


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from bs4 import BeautifulSoup, NavigableString
    from ebooklib import ITEM_DOCUMENT, epub

    from ..textdir import is_rtl_lang
    m = {b.id: b.output_text for b in doc.blocks}
    target = doc.target_lang or cfg.target_lang
    rtl = is_rtl_lang(target)
    book = epub.read_epub(doc.source_path)
    _ensure_toc_uids(book.toc)
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        soup = BeautifulSoup(item.get_content(), "html.parser")
        changed = False
        for n, node in iter_text_nodes(soup):
            t = m.get(f"{item.get_id()}#{n}")
            if t is not None:
                node.replace_with(NavigableString(t))
                changed = True
        # An LTR book translated into an RTL language needs the base direction flipped so readers
        # lay it out right-to-left (set on <html>; harmless if it was already RTL).
        if rtl and soup.html is not None:
            soup.html["dir"] = "rtl"
            if target:
                soup.html["lang"] = str(target)
            changed = True
        if changed:
            item.set_content(str(soup).encode("utf-8"))
    epub.write_epub(out_path, book)
    return out_path
