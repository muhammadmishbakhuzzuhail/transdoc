#!/usr/bin/env python
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Convenience launcher for the web UI + REST API: `python server.py` == `transdoc serve`.

Run from the `backend/` directory (with the venv active). Host/port default to 127.0.0.1:8000
and can be overridden by argument or environment variable:

    python server.py                 # http://127.0.0.1:8000
    python server.py 0.0.0.0 8080    # bind all interfaces on :8080
    TRANSDOC_HOST=0.0.0.0 TRANSDOC_PORT=8080 python server.py

This is a thin wrapper around the same app the CLI serves
(`uvicorn transdoc.api.app:app`); use `transdoc serve` if you prefer the CLI.
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    try:
        import uvicorn
    except ModuleNotFoundError:
        sys.exit(
            "transdoc: the web API needs the 'api' extra. Install it with:\n"
            '    pip install -e ".[api]"'
        )

    argv = sys.argv[1:]
    host = argv[0] if len(argv) >= 1 else os.environ.get("TRANSDOC_HOST", "127.0.0.1")
    port = int(argv[1] if len(argv) >= 2 else os.environ.get("TRANSDOC_PORT", "8000"))

    print(f"transdoc web UI → http://{host}:{port}  (API docs: /docs)")
    uvicorn.run("transdoc.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
