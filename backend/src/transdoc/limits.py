# © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
# Proprietary — source-available for reference only; no use, copying, or
# distribution without written permission. See LICENSE.
"""Resource limits — defensive guards against malicious or pathological input.

A hosted service must not let one upload exhaust memory/CPU: a tiny PDF can declare millions
of pages, a 1 KB zip (docx/xlsx/pptx/epub) can expand to gigabytes, and a small image can
decode to a billion pixels. These guards reject such inputs early with a clear error. All
caps are env-overridable so an operator can tune them.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


MAX_FILE_MB = _env_int("TRANSDOC_MAX_FILE_MB", 300)
MAX_PAGES = _env_int("TRANSDOC_MAX_PAGES", 5000)
MAX_IMAGE_MP = _env_int("TRANSDOC_MAX_IMAGE_MP", 300)        # megapixels for one image
MAX_ZIP_UNCOMPRESSED_MB = _env_int("TRANSDOC_MAX_ZIP_MB", 1000)
MAX_ZIP_RATIO = _env_int("TRANSDOC_MAX_ZIP_RATIO", 200)      # uncompressed / compressed


class InputTooLarge(ValueError):
    """Raised when an input exceeds a safety limit."""


def check_file_size(path: str | Path) -> None:
    mb = Path(path).stat().st_size / 1e6
    if mb > MAX_FILE_MB:
        raise InputTooLarge(f"file is {mb:.0f} MB, exceeds the {MAX_FILE_MB} MB limit")


def check_pages(n: int) -> None:
    if n > MAX_PAGES:
        raise InputTooLarge(f"{n} pages exceeds the {MAX_PAGES}-page limit")


def check_zip_bomb(path: str | Path) -> None:
    """Reject a zip-based document (docx/xlsx/pptx/epub) that decompresses to far more than
    its on-disk size — a classic decompression bomb."""
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            total = sum(i.file_size for i in infos)
            comp = sum(i.compress_size for i in infos) or 1
    except (zipfile.BadZipFile, OSError):
        return  # not a zip / unreadable — other layers handle it
    if total / 1e6 > MAX_ZIP_UNCOMPRESSED_MB:
        raise InputTooLarge(
            f"archive expands to {total / 1e6:.0f} MB, exceeds the "
            f"{MAX_ZIP_UNCOMPRESSED_MB} MB limit")
    if total / 1e6 > 50 and total / comp > MAX_ZIP_RATIO:
        raise InputTooLarge(
            f"archive decompression ratio {total / comp:.0f}x looks like a zip bomb")


def apply_pil_cap() -> None:
    """Cap Pillow's decode size so a small file can't decode into a billion-pixel image."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_MP * 1_000_000
    except Exception:
        pass
