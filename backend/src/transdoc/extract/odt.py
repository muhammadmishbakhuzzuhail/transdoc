"""ODT extraction via odfpy. Headings, paragraphs, lists, tables in document order."""

from __future__ import annotations

from ..config import Config
from ..ir import Block, BlockType, Cell, Confidence, Document, Style, Table
from .base import block_id, reflow_order


def extract(path: str, cfg: Config) -> Document:
    from odf import teletype
    from odf.opendocument import load
    from odf.table import TableCell, TableRow
    from odf.text import P

    doc = load(path)
    out = Document(source_path=path, mime="odt")
    idx = 0

    body = doc.text
    for node in body.childNodes:
        qname = getattr(node, "qname", (None, None))[1]
        if qname == "list":
            # Each list item holds one or more paragraphs -> one LIST_ITEM block per paragraph.
            for p in node.getElementsByType(P):
                content = teletype.extractText(p).strip()
                if not content:
                    continue
                out.blocks.append(
                    Block(id=block_id(0, idx), type=BlockType.LIST_ITEM, text=content,
                          confidence=Confidence(source="digital")))
                idx += 1
        elif qname in ("h", "p"):
            content = teletype.extractText(node).strip()
            if not content:
                continue
            if qname == "h":
                lvl = node.getAttribute("outlinelevel")
                level = int(lvl) if lvl else 1
                btype = BlockType.TITLE if level <= 0 else BlockType.HEADING
            else:
                btype, level = BlockType.PARAGRAPH, 0
            out.blocks.append(
                Block(id=block_id(0, idx), type=btype, text=content,
                      style=Style(heading_level=level),
                      confidence=Confidence(source="digital")))
            idx += 1
        elif qname == "table":
            rows: list[list[Cell]] = []
            for tr in node.getElementsByType(TableRow):
                cells = [Cell(text=teletype.extractText(tc).strip())
                         for tc in tr.getElementsByType(TableCell)]
                if cells:
                    rows.append(cells)
            if rows:
                out.blocks.append(
                    Block(id=block_id(0, idx), type=BlockType.TABLE,
                          table=Table(rows=rows),
                          confidence=Confidence(source="digital")))
                idx += 1

    reflow_order(out)
    return out
