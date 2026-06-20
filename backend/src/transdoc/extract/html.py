# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""HTML extraction via BeautifulSoup.

Previously HTML was routed to the plain-text extractor, which translated the markup literally
(`<p>`, `</div>`, attribute values all became "text"). This parses the DOM instead: scripts/styles
are dropped, block elements become typed IR blocks (headings, paragraphs, list items, table cells),
so only human-readable text is translated and the structure is preserved into Markdown output.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Cell, Confidence, Document, Table
from .base import block_id, reflow_order

_HEADING = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_BLOCK_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote", "td", "th", "caption")
_DROP = ("script", "style", "noscript", "template", "head")


def extract(path: str, cfg: Config) -> Document:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # bs4 absent -> degrade to the plain-text path rather than fail
        from .text import extract as _text_extract
        return _text_extract(path, cfg)

    raw = _read(path)
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(_DROP):
        tag.decompose()

    out = Document(source_path=path, mime="text/html")
    title = soup.find("title")
    if title and title.get_text(strip=True):
        out.metadata = {"title": title.get_text(strip=True)}

    seen_tables: set[int] = set()
    idx = 0
    for el in soup.find_all(_BLOCK_TAGS):
        # a table is emitted whole the first time any of its cells is hit; skip the loose cells
        if el.name in ("td", "th"):
            tbl = el.find_parent("table")
            if tbl is not None and id(tbl) not in seen_tables:
                seen_tables.add(id(tbl))
                t = _table(tbl)
                if t:
                    out.blocks.append(Block(id=block_id(0, idx), type=BlockType.TABLE, page=0,
                                            table=t, confidence=Confidence(source="digital")))
                    idx += 1
            continue
        if el.find_parent("table") is not None:
            continue                      # caption/p inside a table is handled by the table walk
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name in _HEADING:
            btype = BlockType.TITLE if el.name == "h1" else BlockType.HEADING
            lvl = _HEADING[el.name]
        elif el.name == "li":
            btype, lvl = BlockType.LIST_ITEM, 0
        else:
            btype, lvl = BlockType.PARAGRAPH, 0
        b = Block(id=block_id(0, idx), type=btype, page=0, text=txt,
                  confidence=Confidence(source="digital"))
        if lvl:
            b.style.heading_level = lvl
        out.blocks.append(b)
        idx += 1

    if not out.blocks:                    # no recognised block tags -> fall back to flat text
        body = soup.get_text("\n", strip=True)
        if body:
            out.blocks.append(Block(id=block_id(0, 0), type=BlockType.PARAGRAPH, page=0,
                                    text=body, confidence=Confidence(source="digital")))
    reflow_order(out)
    return out


def _table(tbl) -> Table | None:
    rows = []
    for tr in tbl.find_all("tr"):
        if tr.find_parent("table") is not tbl:
            continue
        cells = [Cell(text=c.get_text(" ", strip=True), bold=(c.name == "th"))
                 for c in tr.find_all(["td", "th"]) if c.find_parent("table") is tbl]
        if cells:
            rows.append(cells)
    return Table(rows=rows) if rows else None


def _read(path: str) -> str:
    data = open(path, "rb").read()
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")
