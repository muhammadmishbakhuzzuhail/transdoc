// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { AlertCircle, CheckCircle2, Download, Loader2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { type BatchJob, downloadUrl, getBatch } from "@/lib/api"
import { useI18n } from "@/lib/i18n"

// Batch progress: one row per file, polled together. Jobs run serially server-side, so this is the
// natural "queued -> running -> done" ticker; each finished file gets its own download.
export function BatchView({ bid }: { bid: string }) {
  const { t } = useI18n()
  const [jobs, setJobs] = useState<BatchJob[]>([])
  const poll = useRef<number | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const b = await getBatch(bid)
        if (!alive) return                       // component unmounted mid-request
        setJobs(b.jobs)
        // stop only once there's at least one job AND all are terminal; an empty list ([].every
        // is true) must keep polling, not clear the interval on the first tick.
        if (b.jobs.length > 0 && b.jobs.every((j) => j.status === "done" || j.status === "error")) {
          if (poll.current) clearInterval(poll.current)
        }
      } catch { /* keep polling */ }
    }
    tick()
    poll.current = window.setInterval(tick, 1000)
    return () => { alive = false; if (poll.current) clearInterval(poll.current) }
  }, [bid])

  const done = jobs.filter((j) => j.status === "done").length
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{t("batch_label")} — {done}/{jobs.length} {t("st_done")}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {jobs.map((j) => (
          <div key={j.job_id} className="flex items-center gap-3 rounded-md border p-3">
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{j.filename}</div>
              {j.status === "error"
                ? <div className="flex items-center gap-1 text-xs text-destructive">
                    <AlertCircle className="h-3 w-3" /> {j.message || "failed"}</div>
                : <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                    <div className="h-full bg-primary transition-all"
                      style={{ width: `${Math.round((j.progress ?? 0) * 100)}%` }} /></div>}
            </div>
            {j.status === "queued" && <Badge variant="outline">{t("st_queued")}</Badge>}
            {j.status === "running" && <Loader2 className="h-4 w-4 animate-spin text-primary" />}
            {j.status === "done" && (
              <>
                <CheckCircle2 className="h-4 w-4 text-green-600" />
                <a href={downloadUrl(j.job_id)} aria-label="download translation">
                  <Button size="sm" variant="outline" aria-label="download translation">
                    <Download className="h-4 w-4" />
                  </Button>
                </a>
              </>
            )}
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
