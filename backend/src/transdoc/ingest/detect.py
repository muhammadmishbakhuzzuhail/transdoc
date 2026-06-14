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
        # A page has a usable text layer if it carries enough real text AND a full-page
        # image isn't dominating it. A scan with a tiny stray caption (e.g. a page number)
        # has >20 chars but is really an image — treat it as scanned so it gets OCR'd.
        chars = len(page.get_text("text").strip())
        if chars > 20 and not _image_dominates(page):
            pages_with_text += 1
    doc.close()

    if pages_with_text == 0:
        notes.append(f"0/{n} pages have a text layer -> scanned, OCR required")
        return Kind.PDF_SCAN, notes
    if pages_with_text == n:
        return Kind.PDF_DIGITAL, notes
    notes.append(f"{pages_with_text}/{n} pages have text -> mixed, OCR the rest")
    return Kind.PDF_MIXED, notes


def _image_dominates(page) -> bool:
    """True if the page is really a scan whose only digital text is a stray caption/title, not
    a usable text layer — so it must be OCR'd, not read.

    Two cases, both gated on sparse digital text so a real text page is never misread as a scan:
      - a big image (>60% of the page) with little text (<200 chars), and
      - a moderate image (>35%, e.g. a scan inset within page margins) with title-only text
        (<120 chars). This second case is what a UDHR-style scan trips: a 47-char English
        title over a 37%-coverage image holding the actual (Thai) body — the body would
        otherwise be dropped as a figure and never translated.
    """
    try:
        page_area = abs(page.rect.width * page.rect.height)
        if page_area <= 0:
            return False
        max_cover = 0.0
        for info in page.get_image_info():
            bb = info.get("bbox")
            if not bb:
                continue
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            max_cover = max(max_cover, (w * h) / page_area)
        chars = len(page.get_text("text").strip())
        if max_cover > 0.6 and chars < 200:
            return True
        if max_cover > 0.35 and chars < 120:
            return True
    except Exception:
        return False
    return False


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


def convert_to_docx(path: Path, out_dir: Path, timeout: int = 90) -> Path:
    """Convert legacy .doc / .rtf / .odt to .docx via headless LibreOffice — sandboxed.

    LibreOffice on an untrusted file is a real attack surface (document macros, parser CVEs),
    so we contain it: a throwaway UserInstallation profile (no shared/persistent state, no
    inherited macro config, and it avoids the shared-profile lock that hangs concurrent runs),
    plus OS resource limits (CPU time, address space, output size) applied to the child via a
    POSIX rlimit hook so a malicious doc can't hang or exhaust the host.
    """
    import os
    import shutil
    import tempfile

    out_dir.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="transdoc_lo_")

    preexec = None
    if os.name == "posix":
        import resource

        def preexec():  # runs in the child before exec
            # CPU-time + output-size caps. (No RLIMIT_AS — LibreOffice reserves a large virtual
            # address space and aborts under an AS cap; the wall-clock timeout + CPU limit are
            # what actually bound a hang/CPU-bomb. Cap real memory with a cgroup in production.)
            resource.setrlimit(resource.RLIMIT_CPU, (60, 60))                  # 60 s CPU
            resource.setrlimit(resource.RLIMIT_FSIZE, (512 * 1024 ** 2,) * 2)  # 512 MB output

    try:
        subprocess.run(
            ["soffice", "--headless", "--norestore", "--nolockcheck",
             f"-env:UserInstallation=file://{profile}",
             "--convert-to", "docx", "--outdir", str(out_dir), str(path)],
            check=True, capture_output=True, timeout=timeout, preexec_fn=preexec,
        )
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    out = out_dir / (path.stem + ".docx")
    if not out.exists():
        raise RuntimeError(f"LibreOffice conversion failed for {path}")
    return out
