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
