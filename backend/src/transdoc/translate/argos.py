# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Argos Translate translator — offline, MIT-licensed (commercial-safe fallback).

Wraps OpenNMT models via CTranslate2. Lower quality than NLLB but permissively licensed,
so it is the engine to ship in a commercial open-source release. Models auto-download per
language pair on first use (or pre-bake for air-gapped deployments).
"""

from __future__ import annotations

from ..config import Config


class ArgosTranslator:
    name = "argos"

    def __init__(self):
        import argostranslate.package  # noqa: F401
        import argostranslate.translate  # noqa: F401

    def _ensure_pair(self, src: str, tgt: str):
        import argostranslate.package as pkg

        installed = {(p.from_code, p.to_code) for p in pkg.get_installed_packages()}
        if (src, tgt) in installed:
            return
        pkg.update_package_index()
        for p in pkg.get_available_packages():
            if p.from_code == src and p.to_code == tgt:
                pkg.install_from_path(p.download())
                return

    def translate_batch(self, texts: list[str], cfg: Config,
                        src: str | None = None) -> list[str]:
        if not texts:
            return []
        import argostranslate.translate as tr

        s = (src or "en") if src and src != "auto" else "en"
        t = cfg.target_lang or "en"
        try:
            self._ensure_pair(s, t)
        except Exception:
            pass
        return [tr.translate(x, s, t) for x in texts]
