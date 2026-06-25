# Manual QA checklist (frontend)

The frontend has no automated test/render layer yet — CI only runs `tsc` + `vite build`. Until a
vitest/RTL + a11y suite lands, run this checklist in a real browser before a release (or after a
notable UI change). It targets the areas recent work touched that a type-check can't validate.

How to run:

```bash
cd backend && python server.py        # serves API + built SPA at http://127.0.0.1:8000
# or, for hot-reload dev UI:  cd frontend && npm run dev   (http://localhost:5173)
```

## Theme / no-flash (PR #269)
- [ ] First load in a fresh profile (no `localStorage`) matches the OS theme — **no dark flash**
  for a light-mode OS, no light flash for a dark-mode OS.
- [ ] Toggle theme (header sun/moon) → persists across a hard reload.
- [ ] Throttle the network (DevTools) and reload — the page is not briefly the wrong theme before
  the bundle loads (the pre-paint `index.html` script should win).

## Error boundary (PR #269)
- [ ] App still renders normally end to end (boundary doesn't interfere).
- [ ] Force a render error (e.g. in DevTools temporarily break a component, or feed a malformed
  job) → a recoverable "Something broke" card with a **Reload** button appears, **not** a blank
  white page.

## Language toggle / i18n (PR #273, #276, #277)
- [ ] Header `EN`/`ID` toggle flips the whole visible surface: hero, nav, upload form (all labels,
  options, toggles, submit), result tabs, review panel buttons/status, footer.
- [ ] Choice persists across reload; a fresh `id`-locale browser defaults to Indonesian.
- [ ] No blank labels (un-migrated keys fall back to English, never empty).

## Upload / translate flow
- [ ] Drag-and-drop a file and the click-to-browse path both work; file chips show name + size,
  remove (×) works.
- [ ] Translate a small PDF → progress advances → result header (Download / Report) + tabs appear.
- [ ] Download returns the translated file; Report opens.
- [ ] Trigger a job error (e.g. a junk file) → retry button + a clear message (no raw traceback).

## Review surface (PR #269, #270, #272)
- [ ] Edit a segment → autosaves on blur (saving → saved); reload preserves it.
- [ ] Select a phrase → **synonyms**; **rephrase**; **alternatives** — each lists picks; clicking
  applies; the popover closes with **Esc** and with the × button.
- [ ] Switch **suggestion mode** → already-open suggestion lists clear (no stale results).
- [ ] **Large document (>60 segments)**: scrolling is smooth (virtualized), the source-page
  preview + bbox highlight track the selected segment, and edits committed before scrolling away
  survive. (With the local LLM off, the suggestion buttons return "none" gracefully.)

## Accessibility (PR #270)
- [ ] Keyboard-only: Tab reaches the drop zone, form controls, segment textareas, and the
  suggestion buttons; Esc closes popovers.
- [ ] Screen reader announces icon-only buttons (download, glossary lock/delete, preview
  prev/next, theme toggle, dismiss) by their labels, not just "button".
- [ ] Broken preview image (non-PDF output) shows "preview unavailable", not a broken-image icon.
- [ ] Color contrast is legible in both themes.

## React 19 (PR #275)
- [ ] No new console errors/warnings on load or through the full flow (the upgrade was
  type-clean, but watch for runtime deprecation warnings).
