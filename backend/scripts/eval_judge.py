# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""LLM-as-judge eval: Claude vision scores the pipeline's extraction against the source image.

This automates the manual vision-QA audit. For each document it renders the source to an image,
runs the pipeline's extraction, then asks Claude (vision) to compare the recognized blocks to
what's actually on the page and score: text fidelity, completeness, structure typing, reading
order — plus the specific content that was MISSED or HALLUCINATED. Structure/CER gates catch
regressions; this catches "the extraction is wrong" in ways unlabeled metrics can't.

Needs ANTHROPIC_API_KEY (install the [llm] extra). Online + costs tokens — local/opt-in, like
the other eval tools. Multi-page PDFs are judged on page 1 only.

    cd backend && .venv/bin/python -m scripts.eval_judge corpus/real/full_image/newspaper_scan.jpg
    cd backend && .venv/bin/python -m scripts.eval_judge corpus/real/multilingual/udhr_english.pdf
    cd backend && .venv/bin/python -m scripts.eval_judge --model claude-opus-4-8 <files...>
"""

from __future__ import annotations

import base64
import json
import os
import sys

# Default judge model — the most capable widely released vision model (per the claude-api skill).
_MODEL = "claude-opus-4-8"
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")

# The judge must return exactly this shape — enforced via structured outputs.
_SCHEMA = {
    "type": "object",
    "properties": {
        "text_fidelity": {"type": "integer", "description": "0-100: how accurately the "
                          "recognized text matches the words actually on the page"},
        "completeness": {"type": "integer", "description": "0-100: how much of the page's text "
                         "content was captured (100 = nothing missing)"},
        "structure": {"type": "integer", "description": "0-100: how well block types "
                      "(title/heading/paragraph/table/figure) match the visual structure"},
        "reading_order_ok": {"type": "boolean", "description": "whether the block order follows "
                             "the natural reading order of the page"},
        "missing": {"type": "array", "items": {"type": "string"},
                    "description": "notable text/elements visible on the page but absent from the "
                    "extraction (short quotes/descriptions)"},
        "hallucinated": {"type": "array", "items": {"type": "string"},
                         "description": "text in the extraction that is NOT on the page"},
        "notes": {"type": "string", "description": "one or two sentences on the main issue"},
    },
    "required": ["text_fidelity", "completeness", "structure", "reading_order_ok",
                 "missing", "hallucinated", "notes"],
    "additionalProperties": False,
}

_PROMPT = (
    "You are a QA reviewer for a document-extraction pipeline. The image is the SOURCE document. "
    "Below is what the pipeline EXTRACTED from it (each block as TYPE: text). Compare them and "
    "score how faithfully the extraction reproduces the page. Be strict: reward capturing every "
    "heading/paragraph/table with the right type and reading order; penalise missed text, wrong "
    "block types, bad ordering, and any hallucinated text not on the page. For OCR'd scans, judge "
    "recognised words against what is legibly printed — don't penalise truly illegible regions.\n\n"
    "EXTRACTED BLOCKS:\n{blocks}"
)


def render_to_png(path: str) -> tuple[bytes, str]:
    """Return (png_bytes, media_type) for the source: an image is read as-is; a PDF's first page
    is rasterised."""
    low = path.lower()
    if low.endswith(_IMAGE_EXTS):
        import mimetypes
        mt = mimetypes.guess_type(path)[0] or "image/png"
        with open(path, "rb") as f:
            return f.read(), mt
    if low.endswith(".pdf"):
        import fitz
        d = fitz.open(path)
        try:
            return d[0].get_pixmap(dpi=150).tobytes("png"), "image/png"
        finally:
            d.close()
    raise ValueError(f"unsupported source for judging: {path}")


def extracted_blocks(path: str) -> str:
    """Run the pipeline's extraction and render the blocks as 'TYPE: text' lines (page 1)."""
    from transdoc.config import Config
    from transdoc.extract import extract
    from transdoc.ingest.detect import detect

    doc = extract(detect(path), Config(target_lang="id"))
    lines = []
    for b in sorted(doc.blocks, key=lambda b: (b.page, b.reading_order)):
        if b.page > 0:
            break   # page 1 only (matches the rendered image)
        txt = " ".join((b.text or "").split())
        if txt:
            lines.append(f"{b.type.value}: {txt[:400]}")
    return "\n".join(lines) or "(no blocks extracted)"


def judge(client, model: str, png: bytes, media_type: str, blocks: str) -> dict:
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                             "data": base64.standard_b64encode(png).decode()}},
                {"type": "text", "text": _PROMPT.format(blocks=blocks)},
            ],
        }],
    )
    text = next((b.text for b in msg.content if b.type == "text"), "{}")
    return json.loads(text)


def main(argv: list[str]) -> int:
    model = _MODEL
    if "--model" in argv:
        i = argv.index("--model")
        model = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        sys.stderr.write("usage: eval_judge [--model ID] <file> [<file> ...]\n")
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("ANTHROPIC_API_KEY not set — the LLM judge needs it (pip install '.[llm]').\n")
        return 1
    try:
        import anthropic
    except ImportError:
        sys.stderr.write("anthropic SDK not installed — pip install '.[llm]'.\n")
        return 1

    client = anthropic.Anthropic()
    print(f"LLM-as-judge ({model})  —  extraction vs source\n")
    print(f"{'file':30} {'txt':>4} {'cmpl':>4} {'strc':>4} {'order':>5} {'miss':>4} {'hall':>4}")
    print("-" * 60)
    rows = []
    for path in argv:
        try:
            png, mt = render_to_png(path)
            blocks = extracted_blocks(path)
            v = judge(client, model, png, mt, blocks)
        except Exception as e:  # one bad doc shouldn't sink the run
            print(f"{os.path.basename(path)[:30]:30} ERROR {type(e).__name__}: {e}")
            continue
        rows.append(v)
        name = os.path.basename(path)
        print(f"{name[:30]:30} {v['text_fidelity']:>4} {v['completeness']:>4} "
              f"{v['structure']:>4} {str(v['reading_order_ok'])[:5]:>5} "
              f"{len(v['missing']):>4} {len(v['hallucinated']):>4}")
        if v["missing"]:
            print(f"   missing: {'; '.join(v['missing'][:3])}")
        if v["hallucinated"]:
            print(f"   hallucinated: {'; '.join(v['hallucinated'][:3])}")
        if v["notes"]:
            print(f"   note: {v['notes']}")
    if rows:
        n = len(rows)
        print("-" * 60)
        print(f"{'mean':30} {sum(r['text_fidelity'] for r in rows) // n:>4} "
              f"{sum(r['completeness'] for r in rows) // n:>4} "
              f"{sum(r['structure'] for r in rows) // n:>4}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
