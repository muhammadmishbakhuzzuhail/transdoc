# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""DOCX footnotes / endnotes / comments — the XML parts python-docx doesn't model.

python-docx exposes only the main body, so footnote/endnote/comment text was silently left
untranslated. They live in separate package parts (word/footnotes.xml, endnotes.xml,
comments.xml) which python-docx loads as opaque blobs. This reads their paragraphs (extract) and
writes translations back into the blob (render); both share one paragraph walk + id scheme so they
can never drift.
"""

from __future__ import annotations

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# part filename suffix -> note kind label (also the id prefix). document.xml is included for the
# "textbox" kind only — text-box / shape text (w:txbxContent) the body walk in docx.py misses.
_PARTS = (("footnotes.xml", "footnote"), ("endnotes.xml", "endnote"), ("comments.xml", "comment"),
          ("document.xml", "textbox"))


def _parts(docx_obj):
    """Yield (kind, part) for each present footnotes/endnotes/comments package part."""
    try:
        all_parts = list(docx_obj.part.package.iter_parts())
    except Exception:
        return
    for suffix, kind in _PARTS:
        for part in all_parts:
            if str(part.partname).endswith(suffix):
                yield kind, part
                break


def _para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(f"{_W}t"))


def _set_para_text(p, text: str) -> None:
    ts = list(p.iter(f"{_W}t"))
    if not ts:
        return
    ts[0].text = text
    for t in ts[1:]:
        t.text = ""


def _translatable_paras(root, kind):
    """Yield (pidx, w:p) for the translatable paragraphs of a part, with a deterministic order so
    ids are stable across extract and render.
      - textbox: ONLY paragraphs inside a w:txbxContent (text-box/shape text in document.xml); the
        body paragraphs are handled by docx_inplace, so they must be skipped here.
      - footnote/endnote: skip the separator / continuationSeparator entries (no prose).
      - comment: every non-empty paragraph."""
    pidx = 0
    if kind == "textbox":
        for p in root.iter(f"{_W}p"):
            anc, in_tbx = p.getparent(), False
            while anc is not None:
                if anc.tag == f"{_W}txbxContent":
                    in_tbx = True
                    break
                anc = anc.getparent()
            if in_tbx and _para_text(p).strip():
                yield pidx, p
                pidx += 1
        return
    for p in root.iter(f"{_W}p"):
        anc, drop = p.getparent(), False
        while anc is not None:
            # Skip the separator / continuationSeparator footnotes (no prose). Check the ancestor's
            # tag + type DIRECTLY rather than via an id()-set built in a separate traversal: lxml
            # makes throwaway proxy objects per access, so a freed proxy's id() can be reused by an
            # unrelated element — a real footnote would then collide with a separator and be wrongly
            # dropped (nondeterministic, GC-pressure dependent — it silently lost ALL footnotes).
            if (anc.tag == f"{_W}{kind}"
                    and anc.get(f"{_W}type") in ("separator", "continuationSeparator")):
                drop = True
                break
            anc = anc.getparent()
        if drop or not _para_text(p).strip():
            continue
        yield pidx, p
        pidx += 1


def read_notes(docx_obj) -> list[tuple[str, str, str]]:
    """[(id, text, kind)] for every translatable footnote/endnote/comment paragraph."""
    from lxml import etree
    out: list[tuple[str, str, str]] = []
    for kind, part in _parts(docx_obj):
        try:
            root = etree.fromstring(part.blob)
        except Exception:
            continue
        for pidx, p in _translatable_paras(root, kind):
            out.append((f"note:{kind}:{pidx}", _para_text(p).strip(), kind))
    return out


def write_notes(docx_path: str, by_id: dict[str, str]) -> None:
    """Write translated note text back into a SAVED .docx by rewriting its zip entries.

    Operates on the file (not the python-docx object): setting a part's private blob isn't
    persisted reliably across python-docx versions (passes on 3.11, not 3.12), so we post-process
    the zip directly — version-independent and robust."""
    if not by_id:
        return
    import shutil
    import tempfile
    import zipfile

    from lxml import etree
    with zipfile.ZipFile(docx_path) as zin:
        entries = {n: zin.read(n) for n in zin.namelist()}
    changed_any = False
    for name in list(entries):
        if name.endswith("/_rels") or "_rels" in name:
            continue
        kind = next((k for suffix, k in _PARTS if name.endswith(suffix)), None)
        if kind is None:
            continue
        try:
            root = etree.fromstring(entries[name])
        except Exception:
            continue
        changed = False
        for pidx, p in _translatable_paras(root, kind):
            t = by_id.get(f"note:{kind}:{pidx}")
            if t is not None:
                _set_para_text(p, t)
                changed = True
        if changed:
            entries[name] = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                                           standalone=True)
            changed_any = True
    if not changed_any:
        return
    fd, tmp = tempfile.mkstemp(suffix=".docx")
    import os
    os.close(fd)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)
    shutil.move(tmp, docx_path)
