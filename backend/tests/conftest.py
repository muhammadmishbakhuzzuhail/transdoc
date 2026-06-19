# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Shared test setup.

Disable the cross-run persistent translation memory for the whole test session. Otherwise a
test using the ECHO engine can read a real translation cached by an earlier real run (the cache
is consulted before the engine), so e.g. "Name" comes back as "Nama" instead of echo's "[id]
Name" — a non-deterministic failure that depends on the developer's local TM. Tests must not
depend on that shared cache.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_persistent_tm():
    prev = os.environ.get("TRANSDOC_TM_DISABLE")
    os.environ["TRANSDOC_TM_DISABLE"] = "1"
    yield
    if prev is None:
        os.environ.pop("TRANSDOC_TM_DISABLE", None)
    else:
        os.environ["TRANSDOC_TM_DISABLE"] = prev


@pytest.fixture(autouse=True, scope="session")
def _disable_structured_layout():
    """Force the heuristic extract path in tests: PP-StructureV3 (now the production default) is
    slow + needs paddle, so tests must not take it (fast + deterministic regardless of a local
    layout_venv). Production keeps layout=auto."""
    prev = os.environ.get("TRANSDOC_LAYOUT_DISABLE")
    os.environ["TRANSDOC_LAYOUT_DISABLE"] = "1"
    yield
    if prev is None:
        os.environ.pop("TRANSDOC_LAYOUT_DISABLE", None)
    else:
        os.environ["TRANSDOC_LAYOUT_DISABLE"] = prev
