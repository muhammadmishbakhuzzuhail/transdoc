// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { AlertCircle, Check, Loader2, Replace, Sparkles, Wand2, WrapText } from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  acceptGlossarySuggestion, type FuzzySuggestion, getAlternatives, getHealth, getRephrasings,
  getReview, getSynonyms, type GlossarySuggestion, postCorrection, previewUrl, type ReviewPayload,
  type ReviewSegment,
} from "@/lib/api"

const FALLBACK_STYLES = ["general", "professional", "academic", "friendly", "concise"]

type SaveState = "idle" | "saving" | "saved" | "error"

// CAT-grade review: edit a segment's translation and it autosaves on blur as a confirmed-TM
// correction (DeepL-live). Clicking a segment highlights its region on the source page preview;
// glossary suggestions live in a sidebar with batch-accept.
export function ReviewView({ jid }: { jid: string }) {
  const [review, setReview] = useState<ReviewPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [styles, setStyles] = useState<string[]>(FALLBACK_STYLES)
  const [mode, setMode] = useState("general")     // rephrase/alternatives style preset

  useEffect(() => {
    getReview(jid).then((r) => {
      setReview(r)
      setSelected(r.segments[0]?.block_id ?? null)
    }).catch((e) => setError(e instanceof Error ? e.message : "review not ready"))
    getHealth().then((h) => h.styles?.length && setStyles(h.styles)).catch(() => {})
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
        <div className="flex items-center gap-2 px-0.5 text-xs text-muted-foreground">
          <span>{review.segments.length} segments</span>
          <label className="ml-auto flex items-center gap-1.5">
            Suggestion mode
            <select value={mode} onChange={(e) => setMode(e.target.value)}
              className="rounded-md border bg-background px-2 py-1 text-xs capitalize
                focus:outline-none focus:ring-2 focus:ring-primary">
              {styles.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
        </div>
        {review.segments.length === 0 && (
          <p className="py-8 text-center text-sm text-muted-foreground">No translatable segments.</p>
        )}
        {review.segments.map((seg) => (
          <SegmentRow key={seg.block_id} seg={seg} srcLang={review.src_lang}
            tgtLang={review.tgt_lang} fuzzy={review.fuzzy_suggestions} mode={mode}
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

function SegmentRow({ seg, srcLang, tgtLang, fuzzy, mode, active, onSelect }: {
  seg: ReviewSegment; srcLang: string; tgtLang: string; fuzzy: FuzzySuggestion[]; mode: string
  active: boolean; onSelect: () => void
}) {
  const [value, setValue] = useState(seg.translation)
  const [state, setState] = useState<SaveState>("idle")
  const saved = useRef(seg.translation)
  // mirror of `value` so onBlur saves the LATEST text even when a button click (TM/alt) sets it
  // and blurs in the same tick (the render-time `value` closure would still be stale -> a second
  // postCorrection reverting to the old text).
  const valueRef = useRef(seg.translation)
  const setVal = (v: string) => { valueRef.current = v; setValue(v) }
  const [alts, setAlts] = useState<string[] | null>(null)
  const [loadingAlts, setLoadingAlts] = useState(false)
  // word/phrase synonyms for the current text selection in the textarea
  const taRef = useRef<HTMLTextAreaElement>(null)
  const sel = useRef<{ start: number; end: number }>({ start: 0, end: 0 })
  // the exact span the on-screen synonyms were fetched for — guards against the user editing the
  // textarea while the request is in flight (a stale start/end would splice into the wrong place).
  const synFor = useRef<{ start: number; end: number; phrase: string } | null>(null)
  const [selText, setSelText] = useState("")
  const [syns, setSyns] = useState<string[] | null>(null)
  const [loadingSyns, setLoadingSyns] = useState(false)
  const [reph, setReph] = useState<string[] | null>(null)
  const [loadingReph, setLoadingReph] = useState(false)

  // a TM match whose source equals this segment's source — offer it as a one-click fill
  const match = useMemo(
    () => fuzzy.find((f) => f.source === seg.source && f.match_translation !== seg.translation),
    [fuzzy, seg.source, seg.translation],
  )

  // suggestion mode steers rephrase + alternatives, so any results already on screen are stale once
  // the user switches mode — clear them rather than show results from the previous mode.
  useEffect(() => {
    setAlts(null)
    setReph(null)
    setSyns(null)
  }, [mode])

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
      setAlts(await getAlternatives({ source: seg.source, src_lang: srcLang, tgt_lang: tgtLang,
        style: mode }))
    } catch {
      setAlts([])
    } finally {
      setLoadingAlts(false)
    }
  }

  // remember the current selection inside the textarea so "Synonyms" knows the phrase
  function trackSel() {
    const ta = taRef.current
    if (!ta) return
    sel.current = { start: ta.selectionStart, end: ta.selectionEnd }
    setSelText(value.slice(ta.selectionStart, ta.selectionEnd).trim())
  }

  async function loadSynonyms() {
    const { start, end } = sel.current
    const phrase = value.slice(start, end).trim()
    if (!phrase) return
    synFor.current = { start, end, phrase: value.slice(start, end) }   // pin the raw span
    setLoadingSyns(true)
    try {
      setSyns(await getSynonyms({ phrase, context: value, tgt_lang: tgtLang }))
    } catch {
      setSyns([])
    } finally {
      setLoadingSyns(false)
    }
  }

  function applySynonym(s: string) {
    const span = synFor.current
    // bail if the text shifted under us (edited while the fetch was in flight) — splicing at the
    // stale offsets would corrupt a different part of the sentence.
    if (!span || value.slice(span.start, span.end) !== span.phrase) {
      setSyns(null); setSelText(""); return
    }
    const next = value.slice(0, span.start) + s + value.slice(span.end)   // local override here only
    setVal(next)
    save(next)
    setSyns(null)
    setSelText("")
  }

  async function loadRephrase() {
    setLoadingReph(true)
    try {
      setReph(await getRephrasings({ sentence: value, tgt_lang: tgtLang, style: mode }))
    } catch {
      setReph([])
    } finally {
      setLoadingReph(false)
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
      <textarea ref={taRef} value={value} onChange={(e) => setVal(e.target.value)}
        onFocus={onSelect} onBlur={() => save(valueRef.current)}
        onSelect={trackSel} onMouseUp={trackSel} onKeyUp={trackSel}
        rows={Math.min(6, Math.max(2, Math.ceil(value.length / 60)))}
        className="w-full resize-y rounded-md border bg-background p-2 text-sm
          focus:outline-none focus:ring-2 focus:ring-primary" />
      {match && (
        <button type="button"
          onClick={() => { setVal(match.match_translation); save(match.match_translation) }}
          className="mt-1.5 flex items-center gap-1 text-xs text-primary hover:underline">
          <Sparkles className="h-3 w-3" />
          TM {Math.round(match.score * 100)}%: {match.match_translation}
        </button>
      )}
      <div className="mt-1.5 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <button type="button" onClick={loadAlts} disabled={loadingAlts}
          className="flex items-center gap-1 hover:text-foreground">
          {loadingAlts ? <Loader2 className="h-3 w-3 animate-spin" /> : <Wand2 className="h-3 w-3" />}
          alternatives
        </button>
        <button type="button" onClick={loadRephrase} disabled={loadingReph}
          className="flex items-center gap-1 hover:text-foreground" title={`rephrase (${mode})`}>
          {loadingReph ? <Loader2 className="h-3 w-3 animate-spin" /> : <WrapText className="h-3 w-3" />}
          rephrase
        </button>
        <button type="button" onClick={loadSynonyms} disabled={!selText || loadingSyns}
          className="flex items-center gap-1 enabled:hover:text-foreground disabled:opacity-50"
          title={selText ? `synonyms for "${selText}"` : "select a word in the text first"}>
          {loadingSyns ? <Loader2 className="h-3 w-3 animate-spin" /> : <Replace className="h-3 w-3" />}
          synonyms{selText && `: "${selText.length > 18 ? `${selText.slice(0, 18)}…` : selText}"`}
        </button>
        {((alts && alts.length === 0 && !loadingAlts) || (syns && syns.length === 0 && !loadingSyns)
          || (reph && reph.length === 0 && !loadingReph)) && (
          <span>none (local LLM off?)</span>
        )}
      </div>
      {syns && syns.length > 0 && (
        <Suggestions label={`Replace "${selText}" with`} items={syns}
          onPick={applySynonym} onClose={() => setSyns(null)} />
      )}
      {reph && reph.length > 0 && (
        <Suggestions label={`Rephrase (${mode})`} items={reph}
          onPick={(r) => { setVal(r); save(r); setReph(null) }} onClose={() => setReph(null)} />
      )}
      {alts && alts.length > 0 && (
        <Suggestions label="Alternative translations" items={alts}
          onPick={(a) => { setVal(a); save(a); setAlts(null) }} onClose={() => setAlts(null)} />
      )}
    </div>
  )
}

function Suggestions({ label, items, onPick, onClose }: {
  label: string; items: string[]; onPick: (s: string) => void; onClose: () => void
}) {
  return (
    <div className="mt-1.5 space-y-1 rounded-md border bg-muted/20 p-1.5">
      <div className="flex items-center justify-between px-1 text-[11px] text-muted-foreground">
        <span>{label}</span>
        <button type="button" onClick={onClose} className="hover:text-foreground">✕</button>
      </div>
      {items.map((s, i) => (
        <button key={i} type="button" onClick={() => onPick(s)}
          className="block w-full rounded border border-dashed px-2 py-1 text-left text-xs hover:border-primary hover:bg-primary/5">
          {s}
        </button>
      ))}
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
