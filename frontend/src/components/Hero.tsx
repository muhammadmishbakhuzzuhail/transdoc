// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { FileText, Globe, Layers, ScanLine } from "lucide-react"
import { useI18n } from "@/lib/i18n"

// First-run orientation: a compact hero above the upload form. Kept lightweight so the tool stays
// one page (no separate landing route); the parent hides it once a job is running.
export function Hero() {
  const { t } = useI18n()
  const chips = [
    { icon: FileText, label: "PDF · DOCX · PPTX · XLSX" },
    { icon: ScanLine, label: t("chip_scans") },
    { icon: Layers, label: t("chip_layout") },
    { icon: Globe, label: t("chip_langs") },
  ]
  return (
    <section className="space-y-4 py-2 text-center">
      <h2 className="text-balance text-3xl font-bold tracking-tight sm:text-4xl">
        {t("hero_title_a")}{" "}
        <span className="text-primary">{t("hero_title_b")}</span>
      </h2>
      <p className="mx-auto max-w-xl text-pretty text-muted-foreground">
        {t("hero_sub")}
      </p>
      <ul className="flex flex-wrap items-center justify-center gap-2">
        {chips.map(({ icon: Icon, label }) => (
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
