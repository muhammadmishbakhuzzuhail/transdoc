// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { Check, Download, Lock, LockOpen, Plus, Trash2, Upload } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  acceptGlossarySuggestion, addGlossary, glossaryCsvUrl, type GlossaryEntry,
  type GlossarySuggestionRow, importGlossaryCsv, importTmx, listGlossary, listGlossarySuggestions,
  removeGlossary, tmTmxUrl,
} from "@/lib/api"

// Global glossary manager: every term-pair the system knows, editable in place. Inline rendering
// edits + lock toggles upsert through POST /api/glossary; pending suggestions are batch-accepted.
export function GlossaryView() {
  const [entries, setEntries] = useState<GlossaryEntry[]>([])
  const [sugg, setSugg] = useState<GlossarySuggestionRow[]>([])
  const [picked, setPicked] = useState<Set<string>>(new Set())

  const refresh = () => {
    listGlossary().then(setEntries).catch(() => setEntries([]))
    listGlossarySuggestions().then(setSugg).catch(() => setSugg([]))
  }
  useEffect(refresh, [])

  return (
    <div className="space-y-4">
      <Interchange onChange={refresh} />
      <AddRow onAdded={refresh} />

      <Card>
        <CardHeader><CardTitle>Glossary — {entries.length} terms</CardTitle></CardHeader>
        <CardContent className="space-y-1">
          {entries.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">No terms yet.</p>
          )}
          {entries.map((e) => (
            <Row key={`${e.src_lang}:${e.tgt_lang}:${e.domain}:${e.term}`} e={e} onChange={refresh} />
          ))}
        </CardContent>
      </Card>

      {sugg.length > 0 && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Suggestions ({sugg.length})</CardTitle>
            <Button size="sm" variant="secondary" disabled={!picked.size}
              onClick={async () => {
                await Promise.all([...picked].map((k) => {
                  const s = sugg.find((x) => keyOf(x) === k)!
                  return acceptGlossarySuggestion({
                    term: s.term, src_lang: s.src_lang, tgt_lang: s.tgt_lang, domain: s.domain,
                  }).catch(() => {})
                }))
                setPicked(new Set()); refresh()
              }}>
              <Check className="h-3.5 w-3.5" /> Accept ({picked.size})
            </Button>
          </CardHeader>
          <CardContent className="space-y-1">
            {sugg.map((s) => {
              const k = keyOf(s)
              return (
                <label key={k} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" className="accent-primary" checked={picked.has(k)}
                    onChange={() => setPicked((p) => {
                      const n = new Set(p); n.has(k) ? n.delete(k) : n.add(k); return n
                    })} />
                  <span className="font-medium">{s.term}</span>
                  <span className="text-muted-foreground">→ {s.rendering}</span>
                  <span className="text-xs text-muted-foreground">{s.src_lang}→{s.tgt_lang}
                    {s.domain && ` · ${s.domain}`}</span>
                  <Badge variant="outline" className="ml-auto font-normal">{s.source_kind}</Badge>
                </label>
              )
            })}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

const keyOf = (s: GlossarySuggestionRow) => `${s.src_lang}:${s.tgt_lang}:${s.domain}:${s.term}`

function Interchange({ onChange }: { onChange: () => void }) {
  const [pair, setPair] = useState({ src: "en", tgt: "id" })
  const [msg, setMsg] = useState("")
  const csvRef = useRef<HTMLInputElement>(null)
  const tmxRef = useRef<HTMLInputElement>(null)
  const inp = "w-14 rounded border bg-background px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-2 pt-5 text-sm">
        <a href={glossaryCsvUrl()}>
          <Button size="sm" variant="outline"><Download className="h-4 w-4" /> Glossary CSV</Button>
        </a>
        <input className={inp} value={pair.src} title="src lang for import"
          onChange={(e) => setPair((p) => ({ ...p, src: e.target.value }))} />
        <input className={inp} value={pair.tgt} title="tgt lang for import"
          onChange={(e) => setPair((p) => ({ ...p, tgt: e.target.value }))} />
        <Button size="sm" variant="outline" onClick={() => csvRef.current?.click()}>
          <Upload className="h-4 w-4" /> Import CSV
        </Button>
        <input ref={csvRef} type="file" accept=".csv" className="hidden"
          onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return
            const r = await importGlossaryCsv(f, pair.src, pair.tgt).catch(() => null)
            setMsg(r ? `imported ${r.imported} terms` : "import failed"); onChange()
          }} />
        <span className="mx-1 h-5 w-px bg-border" />
        <a href={tmTmxUrl()}>
          <Button size="sm" variant="outline"><Download className="h-4 w-4" /> TM TMX</Button>
        </a>
        <Button size="sm" variant="outline" onClick={() => tmxRef.current?.click()}>
          <Upload className="h-4 w-4" /> Import TMX
        </Button>
        <input ref={tmxRef} type="file" accept=".tmx,.xml" className="hidden"
          onChange={async (e) => {
            const f = e.target.files?.[0]; if (!f) return
            const r = await importTmx(f).catch(() => null)
            setMsg(r ? `imported ${r.imported} TM units` : "import failed"); onChange()
          }} />
        {msg && <span className="text-xs text-muted-foreground">{msg}</span>}
      </CardContent>
    </Card>
  )
}

function Row({ e, onChange }: { e: GlossaryEntry; onChange: () => void }) {
  const [rendering, setRendering] = useState(e.rendering)
  const save = (locked: boolean, r = rendering) =>
    addGlossary({ term: e.term, rendering: r, src_lang: e.src_lang, tgt_lang: e.tgt_lang,
                  domain: e.domain, locked }).then(onChange)
  return (
    <div className="flex items-center gap-2 rounded-md border p-2 text-sm">
      <span className="w-40 shrink-0 truncate font-medium">{e.term}</span>
      <span className="text-muted-foreground">→</span>
      <input value={rendering} onChange={(ev) => setRendering(ev.target.value)}
        onBlur={() => rendering !== e.rendering && save(!!e.locked)}
        className="flex-1 rounded border bg-background px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary" />
      <span className="w-20 shrink-0 text-xs text-muted-foreground">{e.src_lang}→{e.tgt_lang}</span>
      {e.domain && <Badge variant="outline" className="font-normal">{e.domain}</Badge>}
      <Badge variant={e.origin === "user" ? "default" : "secondary"} className="font-normal">
        {e.origin}</Badge>
      <Button size="icon" variant="ghost" title={e.locked ? "locked" : "unlocked"}
        onClick={() => save(!e.locked)}>
        {e.locked ? <Lock className="h-4 w-4 text-primary" /> : <LockOpen className="h-4 w-4" />}
      </Button>
      <Button size="icon" variant="ghost" title="delete"
        onClick={() => removeGlossary({ term: e.term, src_lang: e.src_lang, tgt_lang: e.tgt_lang,
                                        domain: e.domain }).then(onChange)}>
        <Trash2 className="h-4 w-4 text-destructive" />
      </Button>
    </div>
  )
}

function AddRow({ onAdded }: { onAdded: () => void }) {
  const [f, setF] = useState({ term: "", rendering: "", src_lang: "en", tgt_lang: "id", domain: "" })
  const set = (k: keyof typeof f, v: string) => setF((p) => ({ ...p, [k]: v }))
  const inp = "rounded border bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
  return (
    <Card>
      <CardContent className="flex flex-wrap items-end gap-2 pt-5">
        <input className={`${inp} w-40`} placeholder="term" value={f.term}
          onChange={(e) => set("term", e.target.value)} />
        <input className={`${inp} w-40`} placeholder="rendering" value={f.rendering}
          onChange={(e) => set("rendering", e.target.value)} />
        <input className={`${inp} w-16`} placeholder="src" value={f.src_lang}
          onChange={(e) => set("src_lang", e.target.value)} />
        <input className={`${inp} w-16`} placeholder="tgt" value={f.tgt_lang}
          onChange={(e) => set("tgt_lang", e.target.value)} />
        <input className={`${inp} w-28`} placeholder="domain (opt)" value={f.domain}
          onChange={(e) => set("domain", e.target.value)} />
        <Button size="sm" disabled={!f.term.trim() || !f.rendering.trim()}
          onClick={() => addGlossary({ ...f, locked: false }).then(() => {
            setF({ ...f, term: "", rendering: "" }); onAdded()
          })}>
          <Plus className="h-4 w-4" /> Add
        </Button>
      </CardContent>
    </Card>
  )
}
