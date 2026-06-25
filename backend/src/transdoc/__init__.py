# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""transdoc — CPU-first document translation."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:                                          # single source of truth = the installed package
    __version__ = _pkg_version("transdoc")
except PackageNotFoundError:                  # running from a source tree without an install
    __version__ = "0.1.0"

__all__ = ["__version__"]
