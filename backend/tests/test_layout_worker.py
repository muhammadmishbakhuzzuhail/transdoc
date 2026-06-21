# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Persistent layout worker: routing (persist vs one-shot), JSON parsing, empty shortcut, and the
restart-on-dead-worker decision. The live paddle worker is exercised manually (CI has no paddle);
these cover the protocol/control logic without it."""

from __future__ import annotations

from transdoc.layout.structure import StructRegion, _parse_raw, _Subprocess


def test_parse_raw_builds_regions():
    raw = {"0": [{"label": "text", "bbox": [1, 2, 3, 4], "content": "hi", "order": 0}]}
    out = _parse_raw(raw)
    assert list(out) == [0]
    r = out[0][0]
    assert isinstance(r, StructRegion) and r.label == "text" and r.content == "hi"
    assert (r.x0, r.y0, r.x1, r.y1) == (1, 2, 3, 4)


def test_empty_pnos_never_spawns(monkeypatch):
    s = _Subprocess("python", "en")
    called = []
    monkeypatch.setattr(s, "_served", lambda *a: called.append("served") or {})
    monkeypatch.setattr(s, "_oneshot", lambda *a: called.append("oneshot") or {})

    class _Doc:
        name = "x.pdf"
    assert s.extract_pages(_Doc(), []) == {}
    assert called == []                       # no worker / subprocess for an empty page list


def test_persist_flag_routes(monkeypatch):
    s = _Subprocess("python", "en")
    hits = []
    monkeypatch.setattr(s, "_served", lambda *a: hits.append("served") or {})
    monkeypatch.setattr(s, "_oneshot", lambda *a: hits.append("oneshot") or {})

    class _Doc:
        name = "x.pdf"
    monkeypatch.delenv("TRANSDOC_LAYOUT_PERSIST", raising=False)
    s.extract_pages(_Doc(), [0])
    assert hits[-1] == "served"                                      # default: persistent worker
    monkeypatch.setenv("TRANSDOC_LAYOUT_PERSIST", "0")
    s.extract_pages(_Doc(), [0])
    assert hits[-1] == "oneshot"                                     # opt out -> one-shot


def test_served_restarts_then_falls_through(monkeypatch):
    # both attempts fail -> raises (caller falls back to heuristic); worker stopped each time
    s = _Subprocess("python", "en")
    stops = []
    monkeypatch.setattr(s, "stop", lambda: stops.append(1))
    monkeypatch.setattr(s, "_start", lambda: None)

    def boom(*a):
        raise RuntimeError("worker died")
    monkeypatch.setattr(s, "_request", boom)

    class _Doc:
        name = "x.pdf"
    import pytest
    with pytest.raises(RuntimeError):
        s._served(_Doc(), [0])
    assert len(stops) == 2                     # restarted+retried once, then gave up
