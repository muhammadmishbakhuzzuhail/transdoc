"""Markdown renderer (flow fidelity). Mirrors logical structure from the IR."""

from __future__ import annotations

from ..config import Config
from ..ir import BlockType, Document


def _md_run(run) -> str:
    """One inline run -> markdown, wrapping only the non-space content so markers stay valid."""
    t = run.output_text
    lead = t[:len(t) - len(t.lstrip())]
    trail = t[len(t.rstrip()):]
    core = t.strip()
    if not core:
        return t
    s = run.style
    if s.superscript:
        core = f"<sup>{core}</sup>"
    elif s.subscript:
        core = f"<sub>{core}</sub>"
    if s.bold:
        core = f"**{core}**"
    if s.italic:
        core = f"*{core}*"
    if s.underline:
        core = f"<u>{core}</u>"
    if s.link:
        core = f"[{core}]({s.link})"
    return f"{lead}{core}{trail}"


def _runs_md(runs) -> str:
    return "".join(_md_run(r) for r in runs)


def render(doc: Document, cfg: Config) -> str:
    lines: list[str] = []
    for b in doc.ordered_blocks():
        if b.type == BlockType.TABLE and b.table:
            lines.append(_table(b.table))
            lines.append("")
            continue

        if b.type == BlockType.FIGURE and b.image_path:
            lines.append(f"![figure]({b.image_path})")
            lines.append("")
            continue

        text = _runs_md(b.runs) if b.runs else b.output_text
        text = text.strip()
        if not text:
            continue
        if b.style.underline and b.type in (BlockType.PARAGRAPH, BlockType.CAPTION,
                                            BlockType.LIST_ITEM):
            text = f"<u>{text}</u>"            # markdown has no underline; HTML passthrough
        # carry an inline hyperlink so links survive translation (audit P1)
        if b.style.link and b.type in (BlockType.PARAGRAPH, BlockType.CAPTION, BlockType.LIST_ITEM):
            text = f"[{text}]({b.style.link})"

        # bilingual: show source then translation
        if cfg.bilingual and b.translated is not None and b.text.strip():
            lines.append(f"> {b.text.strip()}")
            lines.append("")
            lines.append(b.translated.strip())
            lines.append("")
            continue

        if b.type == BlockType.TITLE:
            lines.append(f"# {text}")
        elif b.type == BlockType.HEADING:
            lvl = max(2, min(6, b.style.heading_level or 2))
            lines.append(f"{'#' * lvl} {text}")
        elif b.type == BlockType.LIST_ITEM:
            indent = "  " * max(0, b.style.list_level)
            marker = "1." if b.style.list_ordered else "-"
            lines.append(f"{indent}{marker} {text}")
        elif b.type == BlockType.FORMULA:
            # LaTeX (from PP-StructureV3) -> a display-math block; bare text -> code fence.
            looks_latex = any(s in text for s in ("\\", "_{", "^", "frac", "operatorname"))
            lines.append(f"$$\n{text}\n$$" if looks_latex else f"```\n{text}\n```")
        elif b.type == BlockType.CODE:
            lines.append(f"```\n{text}\n```")
        elif b.type == BlockType.CAPTION:
            lines.append(f"*{text}*")
        elif b.type in (BlockType.STAMP, BlockType.SIGNATURE):
            lines.append(f"> [{b.type.value.upper()}] {text}")
        else:
            lines.append(text)

        if b.flags:
            flag_str = "; ".join(f"{k}: {v}" for k, v in b.flags.items())
            lines.append(f"  <!-- ⚠ {flag_str} -->")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _table(table) -> str:
    if not table.rows:
        return ""
    def cells(row):
        return [c.output_text.replace("\n", " ").strip() or " " for c in row]
    out = []
    header = cells(table.rows[0])
    out.append("| " + " | ".join(header) + " |")
    out.append("| " + " | ".join("---" for _ in header) + " |")
    for row in table.rows[1:]:
        out.append("| " + " | ".join(cells(row)) + " |")
    return "\n".join(out)
