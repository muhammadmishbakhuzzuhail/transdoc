"""In-place ODT translation — the in-place strategy for OpenDocument text, mirroring docx.

Re-load the source .odt and swap the translated text into the existing headings, paragraphs,
list items and table cells, walking the body in the exact same order the extractor used so
blocks line up 1:1. Only text content changes, so paragraph styles, lists, tables and the
rest of the document are preserved.

Limitation (same as docx in-place): a paragraph's translation replaces all of its inline
runs, so word-level run formatting inside a paragraph isn't kept — paragraph-level style is.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Document


def _set_text(node, text: str) -> None:
    # Drop child elements (spans) via removeChild so their cache entries clear; plain Text
    # nodes aren't cached and assert in removeChild, so just clear the child list and re-add.
    from odf.element import Element
    for child in list(node.childNodes):
        if isinstance(child, Element):
            node.removeChild(child)
    node.childNodes = []
    node.addText(text)


def _set_cell(cell, text: str) -> None:
    from odf.text import P
    ps = cell.getElementsByType(P)
    if ps:
        _set_text(ps[0], text)
        for p in ps[1:]:
            _set_text(p, "")
    else:
        cell.addElement(P(text=text))


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from odf import teletype
    from odf.opendocument import load
    from odf.table import TableCell, TableRow
    from odf.text import P

    d = load(doc.source_path)
    blocks = doc.ordered_blocks()
    bi = 0

    def take():
        nonlocal bi
        b = blocks[bi] if bi < len(blocks) else None
        bi += 1
        return b

    for node in d.text.childNodes:
        qname = getattr(node, "qname", (None, None))[1]
        if qname == "list":
            for p in node.getElementsByType(P):
                if not teletype.extractText(p).strip():
                    continue              # empty list paragraphs were skipped at extraction
                b = take()
                if b is not None:
                    _set_text(p, b.output_text)
        elif qname in ("h", "p"):
            if not teletype.extractText(node).strip():
                continue
            b = take()
            if b is not None:
                _set_text(node, b.output_text)
        elif qname == "table":
            b = take()
            if b is not None and b.table:
                dcells = [tc for tr in node.getElementsByType(TableRow)
                          for tc in tr.getElementsByType(TableCell)]
                tcells = [c for row in b.table.rows for c in row]
                for dc, tc in zip(dcells, tcells):
                    if tc.text.strip():
                        _set_cell(dc, tc.output_text)

    d.save(out_path)
    return out_path
