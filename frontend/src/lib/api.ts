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
