"""In-place DOCX translation — the DeepL strategy for Office files.

Re-open the *source* .docx and swap the translated text into the existing paragraphs and
table cells, leaving the document structure untouched. Because we only change run text, every
style, image, header/footer, table, list and section stays exactly as authored, and Word's
own layout engine handles the (longer) translated text on open — no overlay, no rebuild.

Limitation: a paragraph's translation is written into its first run (the rest are cleared),
so word-level run variation inside a paragraph (one bold word) is not preserved — translation
breaks the word-to-word alignment that would let us keep it. Paragraph-level style, and
everything else, is preserved.
"""

from __future__ import annotations

from ..config import Config
from ..ir import Document
from ..extract.docx import iter_block_items


def _set_paragraph(paragraph, text: str) -> None:
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(text)
        return
    runs[0].text = text                 # keep run-0 formatting for the whole translation
    for r in runs[1:]:
        r.text = ""


def _set_cell(cell, text: str) -> None:
    paras = cell.paragraphs
    if paras:
        _set_paragraph(paras[0], text)
        for p in paras[1:]:
            for r in p.runs:
                r.text = ""
    else:
        cell.text = text


def render(doc: Document, cfg: Config, out_path: str) -> str:
    from docx import Document as Docx
    from docx.text.paragraph import Paragraph

    d = Docx(doc.source_path)
    blocks = doc.ordered_blocks()
    bi = 0

    for item in iter_block_items(d):
        if isinstance(item, Paragraph):
            if not item.text.strip():
                continue                # empty paragraphs were skipped at extraction time
            if bi >= len(blocks):
                break
            b = blocks[bi]
            bi += 1
            _set_paragraph(item, b.output_text)
        else:  # table — walk cells in the same row/col order the extractor used
            if bi >= len(blocks):
                break
            b = blocks[bi]
            bi += 1
            if b.table:
                tcells = [c for row in b.table.rows for c in row]
                dcells = [c for row in item.rows for c in row.cells]
                for dc, tc in zip(dcells, tcells):
                    if tc.text.strip():
                        _set_cell(dc, tc.output_text)

    d.save(out_path)
    return out_path
