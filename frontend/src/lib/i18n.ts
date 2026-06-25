// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { useSyncExternalStore } from "react"

// Minimal i18n: a flat string table per locale + a tiny external store so any component can read
// the active locale without a context Provider. The UI defaults to the browser language (this is
// an Indonesian-first product). Strings are migrated to t() incrementally — keys fall back to the
// English entry, then to the key itself, so an un-migrated string is never blank.
export type Locale = "en" | "id"

const STRINGS: Record<Locale, Record<string, string>> = {
  en: {
    tagline: "Layout-faithful document translation — CPU-friendly, free.",
    nav_translate: "translate",
    nav_glossary: "glossary",
    tab_review: "Review",
    tab_preview: "Before & after",
    tab_analysis: "Analysis",
    btn_download: "Download",
    btn_report: "Report",
    ready: "Translation ready",
    analysis_unavailable: "Analysis unavailable.",
    lang_label: "Language",
  },
  id: {
    tagline: "Terjemahan dokumen setia tata letak — ringan di CPU, gratis.",
    nav_translate: "terjemah",
    nav_glossary: "glosarium",
    tab_review: "Tinjau",
    tab_preview: "Sebelum & sesudah",
    tab_analysis: "Analisis",
    btn_download: "Unduh",
    btn_report: "Laporan",
    ready: "Terjemahan siap",
    analysis_unavailable: "Analisis tidak tersedia.",
    lang_label: "Bahasa",
  },
}

const KEY = "transdoc-locale"

function detect(): Locale {
  try {
    const saved = localStorage.getItem(KEY)
    if (saved === "en" || saved === "id") return saved
    return navigator.language.toLowerCase().startsWith("id") ? "id" : "en"
  } catch {
    return "en"
  }
}

let locale: Locale = detect()
const listeners = new Set<() => void>()

export function setLocale(l: Locale) {
  locale = l
  try {
    localStorage.setItem(KEY, l)
  } catch {
    /* ignore */
  }
  listeners.forEach((f) => f())
}

function subscribe(cb: () => void) {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

/** `t(key)` for the active locale (falls back to English, then the key). Plus the current locale
 *  and a setter, all reactive via useSyncExternalStore. */
export function useI18n() {
  const l = useSyncExternalStore(subscribe, () => locale)
  const t = (key: string) => STRINGS[l][key] ?? STRINGS.en[key] ?? key
  return { t, locale: l, setLocale }
}
