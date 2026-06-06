"""Plain text / Markdown extraction. Encoding is sniffed, never assumed."""

from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..ir import Block, BlockType, Confidence, Document
from .base import block_id, reflow_order


def extract(path: str, cfg: Config) -> Document:
    raw = Path(path).read_bytes()
    from charset_normalizer import from_bytes

    best = from_bytes(raw).best()
    text = str(best) if best else raw.decode("utf-8", errors="replace")

    out = Document(source_path=path, mime="text/plain")
    idx = 0
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        is_md_heading = para.startswith("#")
        btype = BlockType.HEADING if is_md_heading else BlockType.PARAGRAPH
        out.blocks.append(
            Block(
                id=block_id(0, idx),
                type=btype,
                page=0,
                text=para.lstrip("# ").strip() if is_md_heading else para,
                confidence=Confidence(source="digital"),
            )
        )
        idx += 1
    reflow_order(out)
    return out
