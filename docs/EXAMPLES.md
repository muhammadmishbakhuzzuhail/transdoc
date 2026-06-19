# Examples gallery

Side-by-side **input → output** previews so visitors can see what transdoc produces before running
it. Each row links the source document and its translated result, with a rendered thumbnail.

> **Status: placeholder.** The gallery is generated from the local example corpus. The previews
> below are stubs — they are filled once the example documents have been processed end-to-end (a
> deliberate, on-request step, since it runs the full translation pipeline). Until then, treat the
> table structure as the template.

## How this gallery is built

1. The example inputs live in `backend/corpus/` (local, git-ignored) and
   `backend/src/transdoc/eval/samples/` (committed).
2. Each input is translated with `transdoc translate` (see [USAGE.md](USAGE.md)).
3. Input + output (and a PNG thumbnail of each) are placed under `docs/examples/` and linked here.

## Gallery

| # | Input | Type | Source → Target | Output | Preview |
|---|-------|------|-----------------|--------|---------|
| 1 | _digital PDF_ | PDF (digital) | en → id | _pending_ | _pending_ |
| 2 | _scanned PDF_ | PDF (scan) | hi → id | _pending_ | _pending_ |
| 3 | _DOCX_ | Word | en → id | _pending_ | _pending_ |
| 4 | _form_ | PDF (AcroForm) | en → ar | _pending_ | _pending_ |
| 5 | _photo / image_ | JPG | zh → en | _pending_ | _pending_ |
| 6 | _multilingual_ | PDF (RTL/CJK) | ar → id | _pending_ | _pending_ |

<!--
To fill: for each example, add
  ![input](examples/<name>.in.png)  ![output](examples/<name>.out.png)
and link the actual input/output files. Keep thumbnails small (web-friendly).
-->

---

See also: [USAGE.md](USAGE.md) · [FIDELITY.md](FIDELITY.md)
