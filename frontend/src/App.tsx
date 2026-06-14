import { AlertCircle, ChevronDown, Languages, Loader2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { AnalysisView } from "@/components/AnalysisView"
import { PreviewPanel } from "@/components/PreviewPanel"
import { type FormValues, TranslateForm } from "@/components/TranslateForm"
import { Card, CardContent } from "@/components/ui/card"
import {
  type Analysis, getAnalysis, getHealth, getJob, type Health, type JobStatus, startTranslate,
} from "@/lib/api"

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showDetails, setShowDetails] = useState(false)
  const poll = useRef<number | null>(null)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setError("Backend unreachable. Start it with: transdoc serve"))
    return () => { if (poll.current) clearInterval(poll.current) }
  }, [])

  const busy = job?.status === "queued" || job?.status === "running"

  async function submit(file: File, v: FormValues) {
    setError(null); setAnalysis(null); setJob(null); setShowDetails(false)
    const fd = new FormData()
    fd.append("file", file)
    Object.entries(v).forEach(([k, val]) => fd.append(k, String(val)))
    try {
      const { job_id } = await startTranslate(fd)
      if (poll.current) clearInterval(poll.current)
      poll.current = window.setInterval(async () => {
        const j = await getJob(job_id)
        setJob(j)
        if (j.status === "done") {
          clearInterval(poll.current!)
          getAnalysis(job_id).then(setAnalysis).catch(() => {})
        } else if (j.status === "error") {
          clearInterval(poll.current!)
          setError(j.message || "translation failed")
        }
      }, 700)
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed")
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="flex items-center gap-3">
        <Languages className="h-7 w-7 text-primary" />
        <div>
          <h1 className="text-xl font-bold">transdoc</h1>
          <p className="text-sm text-muted-foreground">
            Layout-faithful document translation — CPU-friendly, free.
          </p>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {[
          ["Free, no limits", "No page, size or watermark caps."],
          ["Handles hard docs", "Scans (OCR), math, diagrams & tables kept verbatim."],
          ["Transparent", "Flags uncertain parts; preview source vs result."],
        ].map(([t, d]) => (
          <div key={t} className="rounded-lg border bg-card p-3">
            <div className="text-sm font-semibold">{t}</div>
            <div className="text-xs text-muted-foreground">{d}</div>
          </div>
        ))}
      </div>

      <TranslateForm health={health} busy={busy} onSubmit={submit} />

      {error && (
        <Card className="border-destructive">
          <CardContent className="flex items-center gap-2 py-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4" /> {error}
          </CardContent>
        </Card>
      )}

      {busy && (
        <Card>
          <CardContent className="space-y-3 py-5">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> {job?.message || "starting…"}
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all"
                style={{ width: `${Math.round((job?.progress ?? 0.1) * 100)}%` }} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* DeepL-style result: before/after preview + Download is the whole beginner flow. */}
      {analysis && job?.status === "done" && <PreviewPanel jid={job.job_id} />}

      {/* Everything technical (flags, glossary, profile, repairs) is opt-in, not in a
          beginner's face. */}
      {analysis && job && (
        <div>
          <button type="button" onClick={() => setShowDetails((s) => !s)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDown className={`h-4 w-4 transition-transform ${showDetails ? "rotate-180" : ""}`} />
            {showDetails ? "Hide details" : "Show details & analysis"}
          </button>
          {showDetails && <div className="mt-4"><AnalysisView jid={job.job_id} a={analysis} /></div>}
        </div>
      )}
    </div>
  )
}
