import { ChevronDown, FileUp, Loader2, Settings2 } from "lucide-react"
import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { Health } from "@/lib/api"

const LANGS = [
  ["id", "Indonesian"], ["en", "English"], ["ar", "Arabic"], ["zh", "Chinese"],
  ["ja", "Japanese"], ["ko", "Korean"], ["de", "German"], ["fr", "French"],
  ["es", "Spanish"], ["ru", "Russian"], ["hi", "Hindi"], ["pt", "Portuguese"],
] as const

export interface FormValues {
  target_lang: string
  source_lang: string
  output_format: string
  engine: string
  fidelity: string
  layout: string
  ocr_engine: string
  register: string
  bilingual: boolean
  quality: boolean
  localize: boolean
  pages: string
}

// Beginner defaults: keep the original format, auto-detect source, auto layout/OCR/engine.
const DEFAULTS: FormValues = {
  target_lang: "id", source_lang: "auto", output_format: "same-as-source", engine: "fallback",
  fidelity: "auto", layout: "auto", ocr_engine: "auto", register: "auto",
  bilingual: false, quality: false, localize: false, pages: "",
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function Picker({ value, onChange, options, labels }: {
  value: string; onChange: (v: string) => void; options: string[]
  labels?: Record<string, string>
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger><SelectValue /></SelectTrigger>
      <SelectContent>
        {options.map((o) => <SelectItem key={o} value={o}>{labels?.[o] ?? o}</SelectItem>)}
      </SelectContent>
    </Select>
  )
}

export function TranslateForm({ health, busy, onSubmit }: {
  health: Health | null
  busy: boolean
  onSubmit: (file: File, v: FormValues) => void
}) {
  const [v, setV] = useState<FormValues>(DEFAULTS)
  const [file, setFile] = useState<File | null>(null)
  const [drag, setDrag] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const set = <K extends keyof FormValues>(k: K, val: FormValues[K]) => setV((p) => ({ ...p, [k]: val }))

  const FORMATS = health?.formats ?? ["same-as-source", "pdf", "docx", "markdown"]

  return (
    <Card>
      <CardContent className="space-y-5 pt-5">
        {/* Drop zone */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]) }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors ${drag ? "border-primary bg-accent" : "border-border"}`}
        >
          <FileUp className="h-8 w-8 text-muted-foreground" />
          <div className="text-sm">
            {file ? <span className="font-medium">{file.name}</span> : "Drop a document or click to browse"}
          </div>
          <p className="text-xs text-muted-foreground">
            PDF (incl. scans), DOCX, PPTX, XLSX, EPUB, images, subtitles
          </p>
          <input ref={inputRef} type="file" className="hidden"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </div>

        {/* The two things a beginner actually chooses */}
        <div className="grid grid-cols-2 gap-4">
          <Field label="Translate to">
            <Picker value={v.target_lang} onChange={(x) => set("target_lang", x)}
              options={LANGS.map((l) => l[0])} labels={Object.fromEntries(LANGS)} />
          </Field>
          <Field label="Output">
            <Picker value={v.output_format} onChange={(x) => set("output_format", x)}
              options={FORMATS}
              labels={{ "same-as-source": "Same as original" }} />
          </Field>
        </div>

        <Button disabled={!file || busy} className="w-full" size="lg"
          onClick={() => file && onSubmit(file, v)}>
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> Working…</> : "Translate"}
        </Button>

        {/* Advanced — hidden by default */}
        <div>
          <button type="button" onClick={() => setAdvanced((a) => !a)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <Settings2 className="h-4 w-4" /> Advanced
            <ChevronDown className={`h-4 w-4 transition-transform ${advanced ? "rotate-180" : ""}`} />
          </button>

          {advanced && (
            <div className="mt-4 space-y-4 rounded-lg border bg-muted/20 p-4">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                <Field label="Source language">
                  <Picker value={v.source_lang} onChange={(x) => set("source_lang", x)}
                    options={["auto", ...LANGS.map((l) => l[0])]}
                    labels={{ auto: "Auto-detect", ...Object.fromEntries(LANGS) }} />
                </Field>
                <Field label="Engine" hint="auto: free chain">
                  <Picker value={v.engine} onChange={(x) => set("engine", x)}
                    options={health?.engines ?? ["fallback"]} />
                </Field>
                <Field label="Fidelity">
                  <Picker value={v.fidelity} onChange={(x) => set("fidelity", x)}
                    options={health?.fidelity ?? ["auto"]} />
                </Field>
                <Field label="Layout model" hint="auto: crop figures/math on PDFs">
                  <Picker value={v.layout} onChange={(x) => set("layout", x)}
                    options={health?.layout ?? ["auto", "off", "paddle"]} />
                </Field>
                <Field label="OCR engine">
                  <Picker value={v.ocr_engine} onChange={(x) => set("ocr_engine", x)}
                    options={health?.ocr ?? ["auto"]} />
                </Field>
                <Field label="Register">
                  <Picker value={v.register} onChange={(x) => set("register", x)}
                    options={health?.register ?? ["auto"]} />
                </Field>
                <Field label="Pages" hint='e.g. "3-7,10"'>
                  <input value={v.pages} onChange={(e) => set("pages", e.target.value)}
                    placeholder="all"
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </Field>
              </div>
              <div className="flex flex-wrap gap-6">
                {([["bilingual", "Bilingual"], ["quality", "Quality flags"], ["localize", "Localize"]] as const).map(
                  ([k, lbl]) => (
                    <label key={k} className="flex items-center gap-2 text-sm">
                      <Switch checked={v[k]} onCheckedChange={(c) => set(k, c)} />
                      {lbl}
                    </label>
                  ),
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
