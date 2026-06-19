# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""EPUB round-trip: translate in place without crashing on the NCX write.

Regression guard: ebooklib drops navPoint ids on read->write, so write_epub raised
`TypeError: Argument must be bytes or unicode, got 'NoneType'`. epub_out backfills the
toc uids before writing.
"""

from __future__ import annotations

import pytest

ebooklib = pytest.importorskip("ebooklib")
pytest.importorskip("bs4")

from ebooklib import ITEM_DOCUMENT, epub  # noqa: E402

from transdoc.config import Config, Engine, OutputFormat  # noqa: E402
from transdoc.pipeline import run  # noqa: E402


def _make_epub(path: str) -> None:
    book = epub.EpubBook()
    book.set_identifier("id1")
    book.set_title("Test Book")
    book.set_language("en")
    c1 = epub.EpubHtml(title="Ch1", file_name="ch1.xhtml", lang="en")
    c1.content = "<html><body><h1>Chapter One</h1><p>First paragraph.</p></body></html>"
    book.add_item(c1)
    book.toc = [c1]
    book.spine = ["nav", c1]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(path, book)


def test_epub_roundtrip_translates_in_place(tmp_path):
    src = tmp_path / "book.epub"
    _make_epub(str(src))
    out = tmp_path / "book.id.epub"
    run(str(src), Config(target_lang="id", engine=Engine.ECHO,
                         output_format=OutputFormat.SAME), str(out))
    assert out.exists()

    book = epub.read_epub(str(out))
    bodies = b"".join(it.get_content() for it in book.get_items_of_type(ITEM_DOCUMENT))
    text = bodies.decode("utf-8")
    assert "[id] Chapter One" in text
    assert "[id] First paragraph." in text


def test_epub_skips_xml_declaration_and_doctype(tmp_path):
    # The <?xml ?> declaration and <!DOCTYPE html> are NavigableString subclasses; they must
    # not be extracted as translatable text (they leaked into markdown/plain output before).
    from bs4 import BeautifulSoup

    from transdoc.extract.epub import iter_text_nodes

    soup = BeautifulSoup(
        "<?xml version='1.0' encoding='utf-8'?><!DOCTYPE html>"
        "<html><body><p>Real text.</p></body></html>",
        "html.parser",
    )
    texts = [str(node).strip() for _, node in iter_text_nodes(soup)]
    assert texts == ["Real text."]
    assert not any("xml" in t.lower() or "doctype" in t.lower() for t in texts)
