// © 2026 Muhammad Mishbakhuz Zuhail. All rights reserved.
// Proprietary — source-available for reference only; no use, copying, or
// distribution without written permission. See LICENSE.
import { AlertCircle, Check, Loader2, Sparkles, Wand2 } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  acceptGlossarySuggestion, type FuzzySuggestion, getAlternatives, getReview,
  type GlossarySuggestion, postCorrection, previewUrl, type ReviewPayload, type ReviewSegment,
} from "@/lib/api"

type SaveState = "idle" | "saving" | "saved" | "error"

// CAT-grade review: edit a segment's translation and it autosaves on blur as a confirmed-TM
// correction (DeepL-live). Clicking a segment highlights its region on the source page preview;
// glossary suggestions live in a sidebar with batch-accept.
export function ReviewView({ jid }: { jid: string }) {
  const [review, setReview] = useState<ReviewPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    getReview(jid).then((r) => {
      setReview(r)
      setSelected(r.segments[0]?.block_id ?? null)
    }).catch((e) => setError(e instanceof Error ? e.message : "review not ready"))
  }, [jid])

  if (error) {
    return (
      <Card className="border-destructive">
        <CardContent className="flex items-center gap-2 py-4 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" /> {error}
        </CardContent>
      </Card>
    )
  }
  if (!review) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading segments…
      </div>
    )
  }

  const sel = review.segments.find((s) => s.block_id === selected) ?? null

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="flex-1 space-y-2">
        {review.segments.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">No translatable segments.</p>
        )}
        {review.segments.map((seg) => (
          <SegmentRow key={seg.block_id} seg={seg} srcLang={review.src_lang}
            tgtLang={review.tgt_lang} fuzzy={review.fuzzy_suggestions}
            active={seg.block_id === selected} onSelect={() => setSelected(seg.block_id)} />
        ))}
      </div>

      <aside className="space-y-4 lg:w-[340px] lg:shrink-0">
        <div className="lg:sticky lg:top-4 space-y-4">
          <SegmentPreview jid={jid} seg={sel} pageSizes={review.page_sizes} />
          <SuggestionsPanel glossary={review.glossary_suggestions}
            fuzzy={review.fuzzy_suggestions} srcLang={review.src_lang} tgtLang={review.tgt_lang} />
        </div>
      </aside>
    </div>
  )
}

function SegmentRow({ seg, srcLang, tgtLang, fuzzy, active, onSelect }: {
  seg: ReviewSegment; srcLang: string; tgtLang: string; fuzzy: FuzzySuggestion[]
  active: boolean; onSelect: () => void
}) {
  const [value, setValue] = useState(seg.translation)
  const [state, setState] = useState<SaveState>("idle")
  const saved = useRef(seg.translation)
  const [alts, setAlts] = useState<string[] | null>(null)
  const [loadingAlts, setLoadingAlts] = useState(false)

  // a TM match whose source equals this segment's source — offer it as a one-click fill
  const match = useMemo(
    () => fuzzy.find((f) => f.source === seg.source && f.match_translation !== seg.translation),
    [fuzzy, seg.source, seg.translation],
  )

  async function save(next: string) {
    if (next.trim() === saved.current.trim()) return
    setState("saving")
    try {
      await postCorrection({ source: seg.source, fix: next, src_lang: srcLang, tgt_lang: tgtLang })
      saved.current = next
      setState("saved")
    } catch {
      setState("error")
    }
  }

  async function loadAlts() {
    setLoadingAlts(true)
    try {
      setAlts(await getAlternatives({ source: seg.source, src_lang: srcLang, tgt_lang: tgtLang }))
    } catch {
      setAlts([])
    } finally {
      setLoadingAlts(false)
    }
  }

  return (
    <div onClick={onSelect}
      className={`rounded-lg border p-3 transition-colors ${active ? "border-primary bg-primary/5" : "bg-card"}`}>
      <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="tabular-nums">p{seg.page + 1}</Badge>
        {seg.flags.map((f) => (
          <Badge key={f} variant="destructive" className="font-normal">{f}</Badge>
        ))}
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
          {state === "saving" && <><Loader2 className="h-3 w-3 animate-spin" /> saving…</>}
          {state === "saved" && <><Check className="h-3 w-3 text-green-600" /> saved</>}
          {state === "error" && <span className="text-destructive">save failed</span>}
        </span>
      </div>
      <p className="mb-2 whitespace-pre-wrap text-sm text-muted-foreground">{seg.source}</p>
      <textarea value={value} onChange={(e) => setValue(e.target.value)}
        onFocus={onSelect} onBlur={() => save(value)}
        rows={Math.min(6, Math.max(2, Math.ceil(value.length / 60)))}
        className="w-full resize-y rounded-md border bg-background p-2 text-sm
          focus:outline-none focus:ring-2 focus:ring-primary" />
      {match && (
        <button type="button"
          onClick={() => { setValue(match.match_translation); save(match.match_translation) }}
          className="mt-1.5 flex items-center gap-1 text-xs text-primary hover:underline">
          <Sparkles className="h-3 w-3" />
          TM {Math.round(match.score * 100)}%: {match.match_translation}
        </button>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-2">
        <button type="button" onClick={loadAlts} disabled={loadingAlts}
          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          {loadingAlts ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />}
          alternatives
        </button>
        {alts && alts.length === 0 && !loadingAlts && (
          <span className="text-xs text-muted-foreground">none (local LLM off?)</span>
        )}
      </div>
      {alts && alts.length > 0 && (
        <div className="mt-1 space-y-1">
          {alts.map((a, i) => (
            <button key={i} type="button"
              onClick={() => { setValue(a); save(a); setAlts(null) }}
              className="block w-full rounded border border-dashed px-2 py-1 text-left text-xs hover:border-primary hover:bg-primary/5">
              {a}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function SegmentPreview({ jid, seg, pageSizes }: {
  jid: string; seg: ReviewSegment | null; pageSizes: Record<string, [number, number]>
}) {
  if (!seg) return null
  const size = pageSizes[String(seg.page)]
  const box = seg.bbox && size
    ? {
        left: `${(seg.bbox[0] / size[0]) * 100}%`,
        top: `${(seg.bbox[1] / size[1]) * 100}%`,
        width: `${((seg.bbox[2] - seg.bbox[0]) / size[0]) * 100}%`,
        height: `${((seg.bbox[3] - seg.bbox[1]) / size[1]) * 100}%`,
      }
    : null
  return (
    <div className="space-y-1">
      <div className="text-xs font-medium text-muted-foreground">Source · page {seg.page + 1}</div>
      <div className="relative overflow-hidden rounded-md border bg-muted/30">
        <img src={previewUrl(jid, "source", seg.page)} alt={`source p${seg.page + 1}`}
          className="w-full object-contain" />
        {box && (
          <div className="pointer-events-none absolute border-2 border-primary bg-primary/20"
            style={box} />
        )}
      </div>
    </div>
  )
}

function SuggestionsPanel({ glossary, fuzzy, srcLang, tgtLang }: {
  glossary: GlossarySuggestion[]; fuzzy: FuzzySuggestion[]; srcLang: string; tgtLang: string
}) {
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [done, setDone] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const pending = glossary.filter((g) => !done.has(g.term))

  function toggle(term: string) {
    setPicked((p) => {
      const n = new Set(p)
      n.has(term) ? n.delete(term) : n.add(term)
      return n
    })
  }

  async function acceptSelected() {
    setBusy(true)
    const terms = [...picked]
    await Promise.all(terms.map((term) =>
      acceptGlossarySuggestion({ term, src_lang: srcLang, tgt_lang: tgtLang }).catch(() => {})))
    setDone((d) => new Set([...d, ...terms]))
    setPicked(new Set())
    setBusy(false)
  }

  if (!pending.length && !fuzzy.length) return null
  return (
    <div className="space-y-3 rounded-lg border bg-card p-3">
      {pending.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Glossary suggestions</span>
            <Button size="sm" variant="secondary" disabled={!picked.size || busy}
              onClick={acceptSelected}>
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              Accept ({picked.size})
            </Button>
          </div>
          <ul className="space-y-1">
            {pending.map((g) => (
              <li key={g.term} className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={picked.has(g.term)}
                  onChange={() => toggle(g.term)} className="accent-primary" />
                <span className="font-medium">{g.term}</span>
                <span className="text-muted-foreground">→ {g.rendering}</span>
                <Badge variant="outline" className="ml-auto font-normal">{g.kind}</Badge>
              </li>
            ))}
          </ul>
        </div>
      )}
      {fuzzy.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-semibold">TM matches ({fuzzy.length})</summary>
          <ul className="mt-2 space-y-1.5">
            {fuzzy.slice(0, 20).map((f, i) => (
              <li key={`${f.source}-${i}`} className="text-xs">
                <span className="tabular-nums text-primary">{Math.round(f.score * 100)}%</span>{" "}
                <span className="text-muted-foreground">{f.match_translation}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}
