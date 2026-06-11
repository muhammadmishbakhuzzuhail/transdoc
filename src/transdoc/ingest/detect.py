"""Format detection + routing.

We never trust the file extension alone. libmagic sniffs the real MIME type, then we map
it to a logical ``Kind`` that the pipeline routes on. For PDFs we additionally probe
whether the pages carry a real text layer or are image-only scans.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Kind(str, Enum):
    PDF_DIGITAL = "pdf_digital"   # PDF with a usable text layer
    PDF_SCAN = "pdf_scan"         # image-only PDF -> OCR
    PDF_MIXED = "pdf_mixed"       # some pages digital, some scanned
    DOCX = "docx"
    DOC = "doc"                   # legacy -> convert via LibreOffice
    ODT = "odt"
    IMAGE = "image"              # png/jpg/tiff -> OCR
    TEXT = "text"               # txt/md
    HTML = "html"
    XLSX = "xlsx"
    PPTX = "pptx"
    RTF = "rtf"
    EPUB = "epub"
    SRT = "srt"                  # SubRip subtitles
    VTT = "vtt"                  # WebVTT subtitles
    UNKNOWN = "unknown"


@dataclass
class Detection:
    kind: Kind
    mime: str
    path: Path
    notes: list[str]


_MIME_MAP = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": Kind.DOCX,
    "application/msword": Kind.DOC,
    "application/vnd.oasis.opendocument.text": Kind.ODT,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": Kind.XLSX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": Kind.PPTX,
    "application/rtf": Kind.RTF,
    "text/rtf": Kind.RTF,
    "application/epub+zip": Kind.EPUB,
    "text/html": Kind.HTML,
    "text/plain": Kind.TEXT,
    "text/markdown": Kind.TEXT,
}


def _sniff_mime(path: Path) -> str:
    try:
        import magic  # python-magic

        return magic.from_file(str(path), mime=True)
    except Exception:
        # Fallback: crude extension map, better than nothing.
        ext = path.suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".odt": "application/vnd.oasis.opendocument.text",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".txt": "text/plain",
            ".md": "text/markdown",
            ".html": "text/html",
        }.get(ext, "application/octet-stream")


def _classify_pdf(path: Path) -> tuple[Kind, list[str]]:
    """Probe each page for a real text layer to tell digital from scanned PDFs."""
    notes: list[str] = []
    try:
        import fitz  # PyMuPDF
    except Exception:
        notes.append("PyMuPDF missing; assuming digital PDF")
        return Kind.PDF_DIGITAL, notes

    doc = fitz.open(str(path))
    pages_with_text = 0
    n = doc.page_count
    for page in doc:
        # Heuristic: a page with > 20 non-space chars has a usable text layer.
        if len(page.get_text("text").strip()) > 20:
            pages_with_text += 1
    doc.close()

    if pages_with_text == 0:
        notes.append(f"0/{n} pages have a text layer -> scanned, OCR required")
        return Kind.PDF_SCAN, notes
    if pages_with_text == n:
        return Kind.PDF_DIGITAL, notes
    notes.append(f"{pages_with_text}/{n} pages have text -> mixed, OCR the rest")
    return Kind.PDF_MIXED, notes


def detect(path: str | Path) -> Detection:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    mime = _sniff_mime(path)
    notes: list[str] = []

    # Subtitles/EPUB sniff as text/plain or zip; trust the extension for these.
    ext_override = {".srt": Kind.SRT, ".vtt": Kind.VTT, ".epub": Kind.EPUB}.get(path.suffix.lower())
    if ext_override:
        return Detection(kind=ext_override, mime=mime, path=path, notes=notes)

    if mime == "application/pdf":
        kind, notes = _classify_pdf(path)
    elif mime.startswith("image/"):
        kind = Kind.IMAGE
    elif mime in _MIME_MAP:
        kind = _MIME_MAP[mime]
    else:
        # zip-based office docs sometimes sniff as application/zip
        if mime == "application/zip":
            ext = path.suffix.lower()
            kind = {".docx": Kind.DOCX, ".odt": Kind.ODT, ".xlsx": Kind.XLSX,
                    ".pptx": Kind.PPTX}.get(ext, Kind.UNKNOWN)
            notes.append(f"sniffed as zip; using extension -> {kind}")
        else:
            kind = Kind.UNKNOWN
            notes.append(f"unrecognized mime: {mime}")

    return Detection(kind=kind, mime=mime, path=path, notes=notes)


def convert_to_docx(path: Path, out_dir: Path) -> Path:
    """Convert legacy .doc / .rtf / .odt to .docx via headless LibreOffice."""
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "docx", "--outdir", str(out_dir), str(path)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    out = out_dir / (path.stem + ".docx")
    if not out.exists():
        raise RuntimeError(f"LibreOffice conversion failed for {path}")
    return out
