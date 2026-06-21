// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { AlertCircle, CheckCircle2, Download, FileText, Languages, Loader2, Moon, RotateCcw, Sun } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { AnalysisView } from "@/components/AnalysisView"
import { BatchView } from "@/components/BatchView"
import { Footer } from "@/components/Footer"
import { GlossaryView } from "@/components/GlossaryView"
import { Hero } from "@/components/Hero"
import { PreviewPanel } from "@/components/PreviewPanel"
import { ReviewView } from "@/components/ReviewView"
import { type FormValues, TranslateForm } from "@/components/TranslateForm"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { useTheme } from "@/lib/theme"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  type Analysis, downloadUrl, getAnalysis, getHealth, getJob, type Health, type JobStatus,
  reportUrl, startBatch, startTranslate,
} from "@/lib/api"

export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [job, setJob] = useState<JobStatus | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [batchId, setBatchId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<"translate" | "glossary">("translate")
  const [theme, toggleTheme] = useTheme()
  const poll = useRef<number | null>(null)
  const lastSubmit = useRef<{ files: File[]; v: FormValues } | null>(null)   // for Retry

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setError("Backend unreachable. Start it with: transdoc serve"))
    return () => { if (poll.current) clearInterval(poll.current) }
  }, [])

  const busy = job?.status === "queued" || job?.status === "running"

  async function submit(files: File[], v: FormValues) {
    lastSubmit.current = { files, v }                // remember for Retry
    setError(null); setAnalysis(null); setJob(null); setBatchId(null)
    if (poll.current) clearInterval(poll.current)   // stop any prior single-job poll (incl. before a batch)
    const fd = new FormData()
    Object.entries(v).forEach(([k, val]) => fd.append(k, String(val)))
    // more than one file -> batch (one job per file, polled as a list); one file -> review-first
    if (files.length > 1) {
      files.forEach((f) => fd.append("files", f))
      try {
        const { batch_id } = await startBatch(fd)
        setBatchId(batch_id)
      } catch (e) {
        setError(e instanceof Error ? e.message : "batch failed")
      }
      return
    }
    fd.append("file", files[0])
    try {
      const { job_id } = await startTranslate(fd)
      poll.current = window.setInterval(async () => {
        // a poll request can fail (network blip, backend restart); without this guard the
        // rejection is unhandled, the interval keeps firing, and the UI hangs on the progress bar.
        try {
          const j = await getJob(job_id)
          setJob(j)
          if (j.status === "done") {
            clearInterval(poll.current!)
            getAnalysis(job_id).then(setAnalysis).catch(() => {})
          } else if (j.status === "error") {
            clearInterval(poll.current!)
            setError(j.message || "translation failed")
          }
        } catch (e) {
          clearInterval(poll.current!)
          setError(e instanceof Error ? e.message : "lost connection to the backend")
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
        <nav className="ml-auto flex items-center gap-1">
          {(["translate", "glossary"] as const).map((tab) => (
            <button key={tab} type="button" onClick={() => setView(tab)}
              className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
                view === tab ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {tab}
            </button>
          ))}
          <Button variant="ghost" size="icon" onClick={toggleTheme} className="ml-1"
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </nav>
      </header>

      {view === "glossary" ? <GlossaryView /> : <>

      {!job && !batchId && !error && <Hero />}

      <TranslateForm health={health} busy={busy} onSubmit={submit} />

      {error && (
        <Card className="border-destructive">
          <CardContent className="flex items-center gap-2 py-4 text-sm text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="flex-1">{error}</span>
            {lastSubmit.current && (
              <Button size="sm" variant="outline"
                onClick={() => { const s = lastSubmit.current!; submit(s.files, s.v) }}>
                <RotateCcw className="h-3.5 w-3.5" /> Retry
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {batchId && <BatchView bid={batchId} />}

      {busy && (
        <Card>
          <CardContent className="space-y-3 py-5">
            <div className="flex items-center gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span className="flex-1 capitalize">{job?.message || "starting…"}</span>
              <span className="tabular-nums text-muted-foreground">
                {Math.round((job?.progress ?? 0.1) * 100)}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full bg-primary transition-all"
                style={{ width: `${Math.round((job?.progress ?? 0.1) * 100)}%` }} />
            </div>
          </CardContent>
        </Card>
      )}

      {/* Review-first: once a job is done, the CAT-grade segment review is the default screen;
          before/after preview, analysis and download live behind secondary tabs. */}
      {job?.status === "done" && (
        <Card className="border-primary/30 bg-accent/40">
          <CardContent className="flex flex-wrap items-center gap-3 py-4">
            <CheckCircle2 className="h-5 w-5 text-primary" />
            <span className="text-sm font-medium">Translation ready</span>
            <div className="ml-auto flex gap-2">
              {job.has_report && (
                <a href={reportUrl(job.job_id)} target="_blank" rel="noreferrer">
                  <Button variant="outline" size="sm"><FileText className="h-4 w-4" /> Report</Button>
                </a>
              )}
              {job.has_output && (
                <a href={downloadUrl(job.job_id)}>
                  <Button size="sm"><Download className="h-4 w-4" /> Download</Button>
                </a>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {job?.status === "done" && (
        <Tabs defaultValue="review" className="space-y-4">
          <TabsList>
            <TabsTrigger value="review">Review</TabsTrigger>
            <TabsTrigger value="preview">Before & after</TabsTrigger>
            <TabsTrigger value="analysis">Analysis</TabsTrigger>
          </TabsList>
          {/* key on job id: force a clean remount per job so the panels' local state (review,
              selections, edited segments, preview page) never bleeds from a previous document */}
          <TabsContent value="review"><ReviewView key={job.job_id} jid={job.job_id} /></TabsContent>
          <TabsContent value="preview"><PreviewPanel key={job.job_id} jid={job.job_id} /></TabsContent>
          <TabsContent value="analysis">
            {analysis
              ? <AnalysisView key={job.job_id} jid={job.job_id} a={analysis} />
              : <p className="py-6 text-sm text-muted-foreground">Analysis unavailable.</p>}
          </TabsContent>
        </Tabs>
      )}
      </>}

      <Footer />
    </div>
  )
}
