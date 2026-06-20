# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""API upload streams with a hard byte cap so an oversized upload can't fill disk before the check."""

from __future__ import annotations

import io
import types

import pytest
from fastapi import HTTPException

from transdoc.api import app as appmod


def _fake_upload(data: bytes, name="big.bin"):
    return types.SimpleNamespace(filename=name, file=io.BytesIO(data))


def test_oversized_upload_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "MAX_FILE_MB", 1, raising=False)
    # patch the limit the function imports at call time
    import transdoc.limits as lim
    monkeypatch.setattr(lim, "MAX_FILE_MB", 1)
    with pytest.raises(HTTPException) as ei:
        appmod._save_upload(_fake_upload(b"x" * (2 * 1024 * 1024)))   # 2 MB > 1 MB cap
    assert ei.value.status_code == 413


def test_small_upload_ok(tmp_path):
    p = appmod._save_upload(_fake_upload(b"hello", "a.txt"))
    assert open(p, "rb").read() == b"hello"
