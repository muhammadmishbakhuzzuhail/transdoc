"""Regeneration dispatch: pick renderer by output format + fidelity."""

from __future__ import annotations

from pathlib import Path

from ..config import Config, Fidelity, OutputFormat
from ..ir import Document


def regenerate(doc: Document, cfg: Config, out_path: str) -> str:
    fmt = cfg.output_format
    src_is_pdf = bool(doc.source_path and doc.source_path.lower().endswith(".pdf"))
    fidelity = cfg.resolve_fidelity(src_is_pdf)

    if fmt == OutputFormat.SAME:
        fmt = OutputFormat.PDF if src_is_pdf else OutputFormat.MARKDOWN

    if fmt == OutputFormat.MARKDOWN or fmt == OutputFormat.PLAIN:
        from .markdown import render

        text = render(doc, cfg)
        Path(out_path).write_text(text, encoding="utf-8")
        return out_path

    if fmt == OutputFormat.DOCX:
        from .docx_out import render

        return render(doc, cfg, out_path)

    if fmt == OutputFormat.PDF:
        from . import pdf_out

        if fidelity == Fidelity.LAYOUT and src_is_pdf:
            return pdf_out.render_overlay(doc, cfg, out_path)
        return pdf_out.render_flow(doc, cfg, out_path)

    raise ValueError(f"unsupported output format: {fmt}")
