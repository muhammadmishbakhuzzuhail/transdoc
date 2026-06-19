# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
"""Interchange formats: TMX (translation memory) + CSV (glossary).

Portability — carry the TM/glossary to and from other CAT tools (Trados, memoQ, OmegaT). TMX 1.4 is
the industry TM exchange XML; CSV (source,target[,domain]) is the common DeepL/CAT glossary format.
Localhost-trust: TMX is parsed from the user's own files (no remote/DTD input).
"""

from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

_XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


# --- TMX (translation memory) ---------------------------------------------------------------

def export_tmx(tm, path: str | Path) -> int:
    """Write all TM entries to a TMX 1.4 file. Returns the count written."""
    pairs = tm.export_pairs()
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<tmx version="1.4">',
           '  <header creationtool="transdoc" creationtoolversion="1.0" segtype="sentence" '
           'o-tmf="transdoc" adminlang="en" srclang="*all*" datatype="plaintext"/>',
           '  <body>']
    for p in pairs:
        sl = p["src_lang"] or "und"
        tl = p["tgt_lang"] or "und"
        out.append("    <tu>")
        out.append(f'      <tuv xml:lang="{escape(sl)}"><seg>{escape(p["src_text"])}</seg></tuv>')
        out.append(f'      <tuv xml:lang="{escape(tl)}"><seg>{escape(p["tgt_text"])}</seg></tuv>')
        out.append("    </tu>")
    out += ["  </body>", "</tmx>"]
    Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(pairs)


def import_tmx(tm, path: str | Path) -> int:
    """Parse a TMX file and load its translation units into the TM. Each <tu> with at least two
    <tuv> contributes (source, target, src_lang, tgt_lang). Returns the count imported."""
    root = ET.parse(path).getroot()
    rows = []
    for tu in root.iter("tu"):
        tuvs = tu.findall("tuv")
        if len(tuvs) < 2:
            continue
        segs = []
        for tuv in tuvs[:2]:
            seg = tuv.find("seg")
            lang = tuv.get(_XML_LANG) or tuv.get("lang") or ""
            text = "".join(seg.itertext()).strip() if seg is not None else ""
            segs.append((text, lang))
        (src, sl), (tgt, tl) = segs[0], segs[1]
        if src and tgt:
            rows.append((src, tgt, sl, tl, ""))
    return tm.import_pairs(rows)


# --- CSV (glossary) -------------------------------------------------------------------------

def export_glossary_csv(gloss, path: str | Path, src_lang: str | None = None,
                        tgt_lang: str | None = None) -> int:
    """Write glossary entries to CSV (source,target,src_lang,tgt_lang,domain). Returns the count."""
    entries = gloss.list(src_lang, tgt_lang)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source", "target", "src_lang", "tgt_lang", "domain"])
        for e in entries:
            w.writerow([e["term"], e["rendering"], e["src_lang"], e["tgt_lang"], e["domain"]])
    return len(entries)


def import_glossary_csv(gloss, path: str | Path, src_lang: str = "", tgt_lang: str = "",
                        domain: str = "") -> int:
    """Load a glossary CSV. Recognises a header; per row, source+target are required. src_lang/
    tgt_lang/domain are taken from the row when present, else from the args (DeepL-style: a CSV for
    one fixed pair). Returns the count added."""
    n = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        rows = list(reader)
    if not rows:
        return 0
    start = 0
    head = [c.strip().lower() for c in rows[0]]
    has_header = "source" in head or "term" in head
    idx = {name: head.index(name) for name in head} if has_header else {}
    if has_header:
        start = 1

    def col(row, *names, default=""):
        for nme in names:
            if nme in idx and idx[nme] < len(row):
                return row[idx[nme]].strip()
        return default

    for row in rows[start:]:
        if not row or len([c for c in row if c.strip()]) < 2:
            continue
        if has_header:
            term = col(row, "source", "term")
            rendering = col(row, "target", "rendering")
            sl = col(row, "src_lang", default=src_lang)
            tl = col(row, "tgt_lang", default=tgt_lang)
            dom = col(row, "domain", default=domain)
        else:
            term, rendering = row[0].strip(), row[1].strip()
            dom = row[2].strip() if len(row) > 2 else domain
            sl, tl = src_lang, tgt_lang
        if term and rendering:
            gloss.add(term, rendering, sl, tl, domain=dom, origin="user")
            n += 1
    return n
