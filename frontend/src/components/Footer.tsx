// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
const REPO = "https://github.com/muhammadmishbakhuzzuhail/transdoc"

export function Footer() {
  return (
    <footer className="mt-4 flex flex-wrap items-center justify-center gap-x-4 gap-y-1
      border-t pt-6 text-xs text-muted-foreground">
      <span>transdoc — layout-faithful document translation</span>
      <span aria-hidden>·</span>
      <a href={`${REPO}/tree/main/docs`} className="hover:text-foreground hover:underline"
        target="_blank" rel="noreferrer">Docs</a>
      <a href={REPO} className="hover:text-foreground hover:underline"
        target="_blank" rel="noreferrer">GitHub</a>
      <a href={`${REPO}/blob/main/LICENSE`} className="hover:text-foreground hover:underline"
        target="_blank" rel="noreferrer">AGPL-3.0</a>
    </footer>
  )
}
