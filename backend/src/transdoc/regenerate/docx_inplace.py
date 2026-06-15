"""In-place DOCX translation — the DeepL strategy for Office files.

Re-open the *source* .docx and swap the translated text into the existing paragraphs and
table cells, leaving the document structure untouched. Because we only change run text, every
style, image, header/footer, table, list and section stays exactly as authored, and Word's
own layout engine handles the (longer) translated text on open — no overlay, no rebuild.

When the block carries inline runs (a paragraph whose text is NOT uniformly styled — a bold word,
a superscript ref, an inline link), the per-run translations are written back as styled runs so
word-level formatting survives. A uniformly-styled paragraph keeps its run-0 formatting for the
whole translation (no rebuild). Paragraph-level style and everything else stay untouched.
"""

from __future__ import annotations

from ..config import Config
from ..extract.docx import iter_block_items
from ..ir import Block, Document


def _set_paragraph(paragraph, b: Block) -> None:
    if getattr(b, "runs", None):
        # mixed-style paragraph: blank the source runs, re-emit the translated runs WITH their
        # captured character style (bold/italic/super/link/...) — preserves inline formatting a
        # flatten-to-run-0 would lose.
        from .docx_out import _add_run
        for r in list(paragraph.runs):
            r.text = ""
        for run in b.runs:
            _add_run(paragraph, run)
        return
    runs = paragraph.runs
    if not runs:
        paragraph.add_run(b.output_text)
        return
    runs[0].text = b.output_text        # uniform paragraph: keep run-0 formatting
    for r in runs[1:]:
        r.text = ""


def _set_cell(cell, text: str) -> None:
    paras = cell.paragraphs
    if paras:
        runs = paras[0].runs
        if runs:
            runs[0].text = text
            for r in runs[1:]:
                r.text = ""
        else:
            paras[0].add_run(text)
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
            _set_paragraph(item, b)
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
