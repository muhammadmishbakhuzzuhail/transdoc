"""Resource-limit guards reject pathological input and pass normal input."""

from __future__ import annotations

import importlib
import zipfile

import pytest


def _reload_with(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    import transdoc.limits as L
    return importlib.reload(L)


def test_page_cap(monkeypatch):
    L = _reload_with(monkeypatch, TRANSDOC_MAX_PAGES=10)
    with pytest.raises(L.InputTooLarge):
        L.check_pages(11)
    L.check_pages(10)          # at the cap is fine


def test_file_size_cap(monkeypatch, tmp_path):
    L = _reload_with(monkeypatch, TRANSDOC_MAX_FILE_MB=1)
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * 2_000_000)
    with pytest.raises(L.InputTooLarge):
        L.check_file_size(big)


def test_zip_bomb_uncompressed_cap(monkeypatch, tmp_path):
    L = _reload_with(monkeypatch, TRANSDOC_MAX_ZIP_MB=1)
    z = tmp_path / "bomb.docx"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("big.txt", b"A" * 5_000_000)   # ~5 MB uncompressed, tiny on disk
    with pytest.raises(L.InputTooLarge):
        L.check_zip_bomb(z)


def test_normal_zip_passes(monkeypatch, tmp_path):
    L = _reload_with(monkeypatch, TRANSDOC_MAX_ZIP_MB=1000)
    z = tmp_path / "ok.docx"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("small.txt", b"hello world")
    L.check_zip_bomb(z)          # no raise


def teardown_module(module):
    # restore default caps for any later test importing limits
    import transdoc.limits
    importlib.reload(transdoc.limits)
