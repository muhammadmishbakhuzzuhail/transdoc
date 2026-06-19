// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
// Thin client for the transdoc FastAPI backend. In dev, /api is proxied by Vite to :8000;
// in a deployed build set VITE_API_BASE to the backend origin.
const BASE = import.meta.env.VITE_API_BASE ?? ""

export interface Health {
  engines: string[]
  formats: string[]
  fidelity: string[]
  ocr: string[]
  register: string[]
  layout: string[]
}

export interface JobStatus {
  job_id: string
  status: "queued" | "running" | "done" | "error"
  progress: number
  message: string
  error: string | null
  meta: Record<string, unknown>
  has_output: boolean
  has_report: boolean
}

export interface FlaggedItem {
  page: number
  type: string
  flags: Record<string, string>
  text: string
  source: string | null
  lang: string | null
}

export interface Analysis {
  profile: {
    input_nature: string
    damage_level: string
    damage_examples: string[]
    source_langs: string[]
    target_lang: string
    genre: string
    structure: string[]
    reading_order: string
    risk_flags: string[]
  }
  counts: { blocks: number; flagged: number; pages: number }
  rendering: { illegible: number; shrunk: number }
  layout: { crops: number; enabled: boolean }
  flagged: FlaggedItem[]
  glossary: { term: string; rendering: string; action: string; rationale: string | null }[]
  repairs: { block_id: string; before: string; after: string; reason: string }[]
}

export async function getHealth(): Promise<Health> {
  const r = await fetch(`${BASE}/api/health`)
  if (!r.ok) throw new Error("health failed")
  return r.json()
}

export async function startTranslate(form: FormData): Promise<{ job_id: string }> {
  const r = await fetch(`${BASE}/api/translate`, { method: "POST", body: form })
  if (!r.ok) throw new Error((await r.text()) || `translate failed (${r.status})`)
  return r.json()
}

export interface BatchJob {
  job_id: string
  filename: string
  status: "queued" | "running" | "done" | "error"
  progress: number
  message: string
  error: string | null
  has_output: boolean
  has_report: boolean
}

export async function startBatch(
  form: FormData,
): Promise<{ batch_id: string; jobs: { job_id: string; filename: string }[] }> {
  const r = await fetch(`${BASE}/api/batch`, { method: "POST", body: form })
  if (!r.ok) throw new Error((await r.text()) || `batch failed (${r.status})`)
  return r.json()
}

export async function getBatch(bid: string): Promise<{ batch_id: string; jobs: BatchJob[] }> {
  const r = await fetch(`${BASE}/api/batch/${bid}`)
  if (!r.ok) throw new Error("batch lookup failed")
  return r.json()
}

export async function getJob(jid: string): Promise<JobStatus> {
  const r = await fetch(`${BASE}/api/jobs/${jid}`)
  if (!r.ok) throw new Error("job lookup failed")
  return r.json()
}

export async function getAnalysis(jid: string): Promise<Analysis> {
  const r = await fetch(`${BASE}/api/analysis/${jid}`)
  if (!r.ok) throw new Error("analysis not ready")
  return r.json()
}

export interface PreviewInfo {
  source: { ok: boolean; pages: number }
  output: { ok: boolean; pages: number }
}

export async function getPreviewInfo(jid: string): Promise<PreviewInfo> {
  const r = await fetch(`${BASE}/api/preview/${jid}/info`)
  if (!r.ok) throw new Error("preview info failed")
  return r.json()
}

export const previewUrl = (jid: string, which: "source" | "output", page: number) =>
  `${BASE}/api/preview/${jid}/${which}/${page}.png`
export const downloadUrl = (jid: string) => `${BASE}/api/download/${jid}`
export const reportUrl = (jid: string) => `${BASE}/api/report/${jid}`

// --- review + feedback (PR-6) ---------------------------------------------------------------

export interface ReviewSegment {
  block_id: string
  page: number
  bbox: [number, number, number, number] | null   // PDF points; map onto the page preview
  source: string
  translation: string
  flags: string[]
}

export interface GlossarySuggestion { term: string; rendering: string; kind: string }

export interface FuzzySuggestion {
  source: string
  match_source: string
  match_translation: string
  score: number
}

export interface ReviewPayload {
  src_lang: string
  tgt_lang: string
  page_sizes: Record<string, [number, number]>     // page -> [width, height] in points
  segments: ReviewSegment[]
  glossary_suggestions: GlossarySuggestion[]
  fuzzy_suggestions: FuzzySuggestion[]
}

export async function getReview(jid: string): Promise<ReviewPayload> {
  const r = await fetch(`${BASE}/api/review/${jid}`)
  if (!r.ok) throw new Error("review not ready")
  return r.json()
}

export interface CorrectionBody {
  source: string
  fix: string
  src_lang: string
  tgt_lang: string
  domain?: string
  term?: boolean       // true -> authoritative glossary; false -> confirmed TM segment
  locked?: boolean
}

export async function postCorrection(
  body: CorrectionBody,
): Promise<{ ok: boolean; scope: string }> {
  const r = await fetch(`${BASE}/api/correct`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.text()) || `correct failed (${r.status})`)
  return r.json()
}

export async function acceptGlossarySuggestion(body: {
  term: string; src_lang: string; tgt_lang: string; domain?: string; locked?: boolean
}): Promise<{ ok: boolean }> {
  const r = await fetch(`${BASE}/api/glossary/suggestions/accept`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.text()) || `accept failed (${r.status})`)
  return r.json()
}

// --- glossary management (PR: glossary manager UI) ------------------------------------------

export interface GlossaryEntry {
  src_lang: string
  tgt_lang: string
  domain: string
  term: string
  rendering: string
  origin: string          // user | confirmed | auto | locked
  locked: number          // 0 | 1
}

export async function listGlossary(filter?: {
  src_lang?: string; tgt_lang?: string; domain?: string
}): Promise<GlossaryEntry[]> {
  const q = new URLSearchParams()
  if (filter?.src_lang) q.set("src_lang", filter.src_lang)
  if (filter?.tgt_lang) q.set("tgt_lang", filter.tgt_lang)
  if (filter?.domain) q.set("domain", filter.domain)
  const r = await fetch(`${BASE}/api/glossary?${q}`)
  if (!r.ok) throw new Error("glossary list failed")
  return (await r.json()).entries
}

export async function addGlossary(body: {
  term: string; rendering: string; src_lang: string; tgt_lang: string
  domain?: string; locked?: boolean
}): Promise<{ ok: boolean }> {
  const r = await fetch(`${BASE}/api/glossary`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error((await r.text()) || `add failed (${r.status})`)
  return r.json()
}

export async function removeGlossary(body: {
  term: string; src_lang: string; tgt_lang: string; domain?: string
}): Promise<{ removed: number }> {
  const r = await fetch(`${BASE}/api/glossary`, {
    method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (!r.ok) throw new Error("remove failed")
  return r.json()
}

export interface GlossarySuggestionRow {
  src_lang: string
  tgt_lang: string
  domain: string
  term: string
  rendering: string
  source_kind: string
}

export async function listGlossarySuggestions(): Promise<GlossarySuggestionRow[]> {
  const r = await fetch(`${BASE}/api/glossary/suggestions`)
  if (!r.ok) throw new Error("suggestions list failed")
  return (await r.json()).suggestions
}

// --- interchange (TMX / CSV) ----------------------------------------------------------------

export const glossaryCsvUrl = () => `${BASE}/api/glossary/export.csv`
export const tmTmxUrl = () => `${BASE}/api/tm/export.tmx`

export async function importGlossaryCsv(
  file: File, src_lang: string, tgt_lang: string, domain = "",
): Promise<{ imported: number }> {
  const fd = new FormData()
  fd.append("file", file); fd.append("src_lang", src_lang)
  fd.append("tgt_lang", tgt_lang); fd.append("domain", domain)
  const r = await fetch(`${BASE}/api/glossary/import`, { method: "POST", body: fd })
  if (!r.ok) throw new Error((await r.text()) || "glossary import failed")
  return r.json()
}

export async function importTmx(file: File): Promise<{ imported: number }> {
  const fd = new FormData()
  fd.append("file", file)
  const r = await fetch(`${BASE}/api/tm/import`, { method: "POST", body: fd })
  if (!r.ok) throw new Error((await r.text()) || "TMX import failed")
  return r.json()
}

// LLM alternative translations (review aid). Returns [] when the local LLM is unavailable (503).
export async function getAlternatives(body: {
  source: string; tgt_lang: string; src_lang?: string; domain?: string; n?: number
}): Promise<string[]> {
  const r = await fetch(`${BASE}/api/alternatives`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  })
  if (r.status === 503) return []
  if (!r.ok) throw new Error("alternatives failed")
  return (await r.json()).alternatives
}
