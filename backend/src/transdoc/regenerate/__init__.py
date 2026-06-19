# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
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
    OutputFormat.ODT: ("odt_inplace", (".odt",)),
}

# When output==SAME, map the source extension to its in-place / round-trip renderer.
_EXT_TO_FORMAT = {
    ".pptx": OutputFormat.PPTX, ".xlsx": OutputFormat.XLSX, ".epub": OutputFormat.EPUB,
    ".srt": OutputFormat.SRT, ".vtt": OutputFormat.VTT,
    ".odt": OutputFormat.ODT, ".docx": OutputFormat.DOCX,
}


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif")
# Office sources we can render natively then convert to PDF via LibreOffice headless.
_SOFFICE_EXTS = (".docx", ".pptx", ".xlsx", ".odt", ".epub")


def _render_native(doc: Document, cfg: Config, out_path: str, ext: str) -> str:
    """Render the translated doc to its native office format (the high-fidelity in-place/round-trip
    renderer), so LibreOffice can then convert that to PDF."""
    from importlib import import_module
    if ext == ".docx":
        src = (doc.source_path or "").lower()
        mod = "docx_inplace" if (src.endswith(".docx") and not cfg.bilingual) else "docx_out"
    else:
        mod = {".pptx": "pptx_out", ".xlsx": "xlsx_out", ".odt": "odt_inplace",
               ".epub": "epub_out"}[ext]
    return import_module(f".{mod}", __package__).render(doc, cfg, out_path)


def _office_to_pdf(doc: Document, cfg: Config, out_path: str) -> str | None:
    """DOCX/PPTX/XLSX/ODT/EPUB source -> PDF the industry-standard way: render the translated
    native file, then LibreOffice headless converts it (keeping the real page layout, far better
    than reflowing to A4). Returns None when soffice or the source type is unavailable so the
    caller falls back to the flow renderer."""
    import os
    import shutil
    import subprocess
    import tempfile
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    src = (doc.source_path or "").lower()
    ext = next((e for e in _SOFFICE_EXTS if src.endswith(e)), None)
    if not soffice or not ext:
        return None
    tmp = tempfile.mkdtemp(prefix="transdoc_soffice_")
    doc.tmp_dirs.append(tmp)                       # pipeline cleans this after the run
    native = os.path.join(tmp, "translated" + ext)
    try:
        _render_native(doc, cfg, native, ext)
        subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, native],
                       capture_output=True, timeout=180, check=True)
        produced = os.path.join(tmp, "translated.pdf")
        if os.path.exists(produced):
            shutil.move(produced, out_path)
            return out_path
    except Exception:
        pass
    return None


def regenerate(doc: Document, cfg: Config, out_path: str) -> str:
    fmt = cfg.output_format
    src = (doc.source_path or "").lower()
    src_is_pdf = src.endswith(".pdf")
    src_is_image = doc.mime == "image" or src.endswith(_IMAGE_EXTS)
    # An image source can preserve layout the same way a PDF can (overlay on the original).
    fidelity = cfg.resolve_fidelity(src_is_pdf or src_is_image)

    # Image source, layout fidelity: Lens-style overlay on the original. same-as-source ->
    # a translated image (out_path keeps the source ext); -> pdf gives an image-backed PDF.
    # render_image_overlay picks raster vs PDF from out_path's extension.
    if src_is_image and fidelity == Fidelity.LAYOUT and fmt in (
            OutputFormat.SAME, OutputFormat.PDF):
        from . import pdf_out

        return pdf_out.render_image_overlay(doc, cfg, out_path)

    if fmt == OutputFormat.SAME:
        src_ext = "." + src.rsplit(".", 1)[-1] if "." in src else ""
        if src_ext in _EXT_TO_FORMAT:
            fmt = _EXT_TO_FORMAT[src_ext]
        elif src_is_pdf:
            fmt = OutputFormat.PDF
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
        # docx source -> mutate it in place (DeepL-style: keep all formatting, only swap text).
        # Any other source (PDF/image/...) has no docx to mutate, so rebuild one from the IR.
        # Bilingual output also rebuilds (it needs to interleave source + translation).
        if src.endswith(".docx") and not cfg.bilingual:
            from .docx_inplace import render as render_inplace

            return render_inplace(doc, cfg, out_path)
        from .docx_out import render

        return render(doc, cfg, out_path)

    if fmt == OutputFormat.PDF:
        from . import pdf_out

        # image + LAYOUT + PDF is handled by the early return above; here LAYOUT means PDF src
        if fidelity == Fidelity.LAYOUT and src_is_pdf:
            return pdf_out.render_overlay(doc, cfg, out_path)
        # RECONSTRUCT (the PDF AUTO default): positioned per-page rebuild keeping source page
        # size/count/positions. Needs source page geometry, so only for a PDF source.
        if fidelity == Fidelity.RECONSTRUCT and src_is_pdf and doc.page_sizes:
            return pdf_out.render_reconstruct(doc, cfg, out_path)
        # Office source -> PDF: render the translated native file, then LibreOffice -> PDF (keeps
        # the real layout). Falls back to the A4 flow renderer when soffice/source isn't available.
        via = _office_to_pdf(doc, cfg, out_path)
        if via:
            return via
        return pdf_out.render_flow(doc, cfg, out_path)

    raise ValueError(f"unsupported output format: {fmt}")
