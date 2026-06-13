"""ODT list extraction: <text:list> items must become LIST_ITEM blocks, not be dropped.

Regression guard: the ODT extractor only handled top-level h/p/table nodes, so list
paragraphs (wrapped in <text:list>/<text:list-item>) silently vanished from the IR.
"""

from __future__ import annotations

import pytest

pytest.importorskip("odf")

from odf.opendocument import OpenDocumentText  # noqa: E402
from odf.text import H, List, ListItem, P  # noqa: E402

from transdoc.config import Config  # noqa: E402
from transdoc.extract.odt import extract  # noqa: E402
from transdoc.ir import BlockType  # noqa: E402


def _make_odt(path: str) -> None:
    doc = OpenDocumentText()
    doc.text.addElement(H(outlinelevel=1, text="Heading"))
    doc.text.addElement(P(text="A paragraph."))
    lst = List()
    for label in ("First bullet", "Second bullet"):
        item = ListItem()
        item.addElement(P(text=label))
        lst.addElement(item)
    doc.text.addElement(lst)
    doc.save(path)


def test_odt_extracts_list_items(tmp_path):
    src = tmp_path / "doc.odt"
    _make_odt(str(src))
    out = extract(str(src), Config(target_lang="id"))
    items = [b.text for b in out.blocks if b.type == BlockType.LIST_ITEM]
    assert items == ["First bullet", "Second bullet"]
