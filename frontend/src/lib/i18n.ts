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
    drop_doc: "Drop a document",
    or_browse: "or click to browse",
    files_selected: "selected — click to change",
    file_one: "1 file",
    filetypes: "PDF (incl. scans), DOCX, PPTX, XLSX, EPUB, images, subtitles — one or many",
    f_translate_to: "Translate to",
    f_output: "Output",
    opt_same: "Same as original",
    opt_auto: "Auto-detect",
    working: "Working…",
    translate: "Translate",
    advanced: "Advanced",
    f_source: "Source language",
    f_engine: "Engine",
    hint_engine: "auto: free chain",
    f_fidelity: "Fidelity",
    f_layout: "Layout model",
    hint_layout: "auto: crop figures/math on PDFs",
    f_ocr: "OCR engine",
    f_register: "Register",
    f_pages: "Pages",
    ph_all: "all",
    tog_bilingual: "Bilingual",
    tog_quality: "Quality flags",
    tog_localize: "Localize",
    tog_align: "Style alignment",
    tog_escalate: "LLM escalation",
    tog_repair: "OCR repair",
    hero_title_a: "Translate any document,",
    hero_title_b: "keep the layout.",
    hero_sub: "Upload a PDF, Office file, or a scan — transdoc extracts, translates, and rebuilds a faithful copy in your language. CPU-friendly, free, and runs locally.",
    chip_scans: "Scans & images (OCR)",
    chip_layout: "Layout preserved",
    chip_langs: "40+ languages",
    footer_tagline: "transdoc — layout-faithful document translation",
    rv_loading: "Loading segments…",
    rv_segments: "segments",
    rv_mode: "Suggestion mode",
    rv_none: "No translatable segments.",
    rv_alternatives: "alternatives",
    rv_rephrase: "rephrase",
    rv_synonyms: "synonyms",
    rv_saving: "saving…",
    rv_saved: "saved",
    rv_save_failed: "save failed",
    an_title: "Analysis",
    st_pages: "pages",
    st_blocks: "blocks",
    st_flagged: "flagged",
    st_crops: "region crops",
    st_illegible: "illegible",
    st_repairs: "repairs",
    tab_profile: "Profile",
    tab_flagged: "Flagged",
    tab_glossary: "Glossary",
    tab_repairs: "Repairs",
    r_input_nature: "Input nature",
    r_damage: "Damage level",
    r_source_langs: "Source language(s)",
    r_target_lang: "Target language",
    r_genre: "Genre",
    r_reading_order: "Reading order",
    r_layout_model: "Layout model",
    lay_on: "on (paddle)",
    lay_off: "off (heuristics)",
    r_structure: "Structure",
    r_risk_flags: "Risk flags",
    e_clean: "Nothing flagged — clean run.",
    e_no_glossary: "No glossary terms resolved.",
    e_no_repairs: "No reconstruction repairs.",
    batch_label: "Batch",
    st_done: "done",
    st_queued: "queued",
    gl_terms_n: "terms",
    gl_suggestions: "Suggestions",
    gl_accept_all: "Accept all",
    gl_add: "Add",
    gl_ph_term: "term",
    gl_ph_rendering: "rendering",
    gl_ph_domain: "domain (optional)",
    gl_import_csv: "Import CSV",
    gl_export_csv: "Export CSV",
    gl_export_tmx: "Export TMX (TM)",
    gl_accept: "Accept",
    gl_import_tmx: "Import TMX",
    gl_empty: "No glossary terms yet.",
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
    drop_doc: "Jatuhkan dokumen",
    or_browse: "atau klik untuk pilih",
    files_selected: "dipilih — klik untuk ganti",
    file_one: "1 berkas",
    filetypes: "PDF (termasuk hasil pindai), DOCX, PPTX, XLSX, EPUB, gambar, subtitle — satu atau banyak",
    f_translate_to: "Terjemahkan ke",
    f_output: "Keluaran",
    opt_same: "Sama seperti asli",
    opt_auto: "Deteksi otomatis",
    working: "Memproses…",
    translate: "Terjemahkan",
    advanced: "Lanjutan",
    f_source: "Bahasa sumber",
    f_engine: "Mesin",
    hint_engine: "auto: rantai gratis",
    f_fidelity: "Kesetiaan",
    f_layout: "Model tata letak",
    hint_layout: "auto: pangkas gambar/rumus di PDF",
    f_ocr: "Mesin OCR",
    f_register: "Ragam",
    f_pages: "Halaman",
    ph_all: "semua",
    tog_bilingual: "Dwibahasa",
    tog_quality: "Penanda kualitas",
    tog_localize: "Lokalisasi",
    tog_align: "Penyelarasan gaya",
    tog_escalate: "Eskalasi LLM",
    tog_repair: "Perbaikan OCR",
    hero_title_a: "Terjemahkan dokumen apa pun,",
    hero_title_b: "tata letak tetap utuh.",
    hero_sub: "Unggah PDF, berkas Office, atau hasil pindai — transdoc mengekstrak, menerjemahkan, dan membangun ulang salinan setia dalam bahasamu. Ringan di CPU, gratis, dan berjalan lokal.",
    chip_scans: "Pindaian & gambar (OCR)",
    chip_layout: "Tata letak terjaga",
    chip_langs: "40+ bahasa",
    footer_tagline: "transdoc — terjemahan dokumen setia tata letak",
    rv_loading: "Memuat segmen…",
    rv_segments: "segmen",
    rv_mode: "Mode saran",
    rv_none: "Tidak ada segmen yang dapat diterjemahkan.",
    rv_alternatives: "alternatif",
    rv_rephrase: "ubah frasa",
    rv_synonyms: "sinonim",
    rv_saving: "menyimpan…",
    rv_saved: "tersimpan",
    rv_save_failed: "gagal simpan",
    an_title: "Analisis",
    st_pages: "halaman",
    st_blocks: "blok",
    st_flagged: "ditandai",
    st_crops: "potongan area",
    st_illegible: "tak terbaca",
    st_repairs: "perbaikan",
    tab_profile: "Profil",
    tab_flagged: "Ditandai",
    tab_glossary: "Glosarium",
    tab_repairs: "Perbaikan",
    r_input_nature: "Sifat masukan",
    r_damage: "Tingkat kerusakan",
    r_source_langs: "Bahasa sumber",
    r_target_lang: "Bahasa tujuan",
    r_genre: "Genre",
    r_reading_order: "Urutan baca",
    r_layout_model: "Model tata letak",
    lay_on: "aktif (paddle)",
    lay_off: "mati (heuristik)",
    r_structure: "Struktur",
    r_risk_flags: "Tanda risiko",
    e_clean: "Tidak ada yang ditandai — proses bersih.",
    e_no_glossary: "Tidak ada istilah glosarium yang diterapkan.",
    e_no_repairs: "Tidak ada perbaikan rekonstruksi.",
    batch_label: "Batch",
    st_done: "selesai",
    st_queued: "antre",
    gl_terms_n: "istilah",
    gl_suggestions: "Saran",
    gl_accept_all: "Terima semua",
    gl_add: "Tambah",
    gl_ph_term: "istilah",
    gl_ph_rendering: "terjemahan",
    gl_ph_domain: "domain (opsional)",
    gl_import_csv: "Impor CSV",
    gl_export_csv: "Ekspor CSV",
    gl_export_tmx: "Ekspor TMX (TM)",
    gl_accept: "Terima",
    gl_import_tmx: "Impor TMX",
    gl_empty: "Belum ada istilah glosarium.",
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
