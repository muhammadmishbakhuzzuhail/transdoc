// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { FileText, Globe, Layers, ScanLine } from "lucide-react"

const CHIPS = [
  { icon: FileText, label: "PDF · DOCX · PPTX · XLSX" },
  { icon: ScanLine, label: "Scans & images (OCR)" },
  { icon: Layers, label: "Layout preserved" },
  { icon: Globe, label: "40+ languages" },
]

// First-run orientation: a compact hero above the upload form. Kept lightweight so the tool stays
// one page (no separate landing route); the parent hides it once a job is running.
export function Hero() {
  return (
    <section className="space-y-4 py-2 text-center">
      <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
        Translate any document,{" "}
        <span className="text-primary">keep the layout.</span>
      </h2>
      <p className="mx-auto max-w-xl text-pretty text-muted-foreground">
        Upload a PDF, Office file, or a scan — transdoc extracts, translates, and rebuilds a
        faithful copy in your language. CPU-friendly, free, and runs locally.
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-2">
        {CHIPS.map(({ icon: Icon, label }) => (
          <li key={label}
            className="inline-flex items-center gap-1.5 rounded-full border bg-card px-3 py-1
              text-xs font-medium text-muted-foreground">
            <Icon className="h-3.5 w-3.5 text-primary" aria-hidden /> {label}
          </li>
        ))}
      </ul>
    </section>
  )
}
