"""Subtitle extraction (SRT / WebVTT).

A cue = index/timestamp header lines + one or more text lines. We only ever touch the TEXT
lines; headers (timestamps, cue ids, the WEBVTT preamble) are preserved verbatim so the
round-trip keeps timing exact. Each cue becomes one IR block with a stable id (``cue{n}``);
the renderer re-parses the source and swaps text by id.
"""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..ir import Block, BlockType, Confidence, Document
from .base import reflow_order


def _read(path: str) -> str:
    raw = Path(path).read_bytes()
    from charset_normalizer import from_bytes

    best = from_bytes(raw).best()
    return str(best) if best else raw.decode("utf-8", errors="replace")


def parse_cues(text: str) -> list[dict]:
    """Return cues as {header: [lines], text: [lines]}. Blank-line separated blocks; a line
    containing '-->' (and anything before it, e.g. an SRT index) is header, the rest is text.
    A leading WEBVTT/NOTE/STYLE block with no '-->' is treated as all-header (preamble)."""
    cues: list[dict] = []
    for raw_block in text.replace("\r\n", "\n").split("\n\n"):
        block = raw_block.strip("\n")
        if not block.strip():
            continue
        lines = block.split("\n")
        ts_idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if ts_idx is None:
            cues.append({"header": lines, "text": []})  # preamble / NOTE / STYLE
        else:
            cues.append({"header": lines[: ts_idx + 1], "text": lines[ts_idx + 1 :]})
    return cues


def compose_cues(cues: list[dict]) -> str:
    out = []
    for c in cues:
        out.append("\n".join(list(c["header"]) + list(c["text"])))
    return "\n\n".join(out) + "\n"


def extract(path: str, cfg: Config) -> Document:
    text = _read(path)
    out = Document(source_path=path, mime="text/plain")
    for i, cue in enumerate(parse_cues(text)):
        body = "\n".join(cue["text"]).strip()
        if not body:
            continue
        out.blocks.append(
            Block(id=f"cue{i}", type=BlockType.PARAGRAPH, page=0, text=body,
                  confidence=Confidence(source="digital"))
        )
    reflow_order(out)
    return out
