"""Regeneration dispatch: pick renderer by output format + fidelity."""

from __future__ import annotations

from pathlib import Path

from ..config import Config, Fidelity, OutputFormat
from ..ir import Document


# Round-trip formats: reopen the source and swap text in place, keeping all structure.
_ROUNDTRIP = {
    OutputFormat.PPTX: ("pptx_out", (".pptx",)),
    OutputFormat.XLSX: ("xlsx_out", (".xlsx",)),
    OutputFormat.EPUB: ("epub_out", (".epub",)),
    OutputFormat.SRT: ("subtitle_out", (".srt", ".vtt")),
    OutputFormat.VTT: ("subtitle_out", (".srt", ".vtt")),
}

# When output==SAME, map the source extension to the round-trip renderer.
_EXT_TO_FORMAT = {
    ".pptx": OutputFormat.PPTX, ".xlsx": OutputFormat.XLSX, ".epub": OutputFormat.EPUB,
    ".srt": OutputFormat.SRT, ".vtt": OutputFormat.VTT,
}


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def regenerate(doc: Document, cfg: Config, out_path: str) -> str:
    fmt = cfg.output_format
    src = (doc.source_path or "").lower()
    src_is_pdf = src.endswith(".pdf")
    src_is_image = doc.mime == "image" or src.endswith(_IMAGE_EXTS)
    # An image source can preserve layout the same way a PDF can (overlay on the original).
    fidelity = cfg.resolve_fidelity(src_is_pdf or src_is_image)

    if fmt == OutputFormat.SAME:
        src_ext = "." + src.rsplit(".", 1)[-1] if "." in src else ""
        if src_ext in _EXT_TO_FORMAT:
            fmt = _EXT_TO_FORMAT[src_ext]
        elif src_is_pdf or src_is_image:
            fmt = OutputFormat.PDF  # image -> image-backed PDF overlay
        else:
            fmt = OutputFormat.MARKDOWN

    # round-trip renderers (pptx/xlsx/epub/subtitles) — require a matching source file
    if fmt in _ROUNDTRIP:
        mod_name, exts = _ROUNDTRIP[fmt]
        if not src.endswith(exts):
            raise ValueError(f"{fmt.value} output requires a {' or '.join(exts)} source")
        from importlib import import_module

        mod = import_module(f".{mod_name}", __package__)
        return mod.render(doc, cfg, out_path)

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

        if fidelity == Fidelity.LAYOUT and src_is_image:
            return pdf_out.render_image_overlay(doc, cfg, out_path)
        if fidelity == Fidelity.LAYOUT and src_is_pdf:
            return pdf_out.render_overlay(doc, cfg, out_path)
        return pdf_out.render_flow(doc, cfg, out_path)

    raise ValueError(f"unsupported output format: {fmt}")
