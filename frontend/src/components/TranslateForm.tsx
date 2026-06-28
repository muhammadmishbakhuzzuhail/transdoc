// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { ChevronDown, FileUp, Loader2, Settings2, X } from "lucide-react"
import { useRef, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import type { Health } from "@/lib/api"
import { useI18n } from "@/lib/i18n"

// Curated target/source languages. Indonesian first (default audience); the rest span the major
// scripts so the "40+ languages" claim is real and a user can actually pick them (the old 12-item
// list both under-served users and made the marketing chip false). The engines support far more —
// any ISO code works at the API/CLI — this is just the common-case UI shortlist.
const LANGS = [
  ["id", "Indonesian"], ["en", "English"], ["ar", "Arabic"], ["zh", "Chinese"],
  ["ja", "Japanese"], ["ko", "Korean"], ["de", "German"], ["fr", "French"],
  ["es", "Spanish"], ["pt", "Portuguese"], ["it", "Italian"], ["nl", "Dutch"],
  ["ru", "Russian"], ["uk", "Ukrainian"], ["pl", "Polish"], ["cs", "Czech"],
  ["ro", "Romanian"], ["el", "Greek"], ["tr", "Turkish"], ["sv", "Swedish"],
  ["da", "Danish"], ["fi", "Finnish"], ["no", "Norwegian"], ["hu", "Hungarian"],
  ["bg", "Bulgarian"], ["hr", "Croatian"], ["sr", "Serbian"], ["sk", "Slovak"],
  ["hi", "Hindi"], ["bn", "Bengali"], ["ta", "Tamil"], ["te", "Telugu"],
  ["ur", "Urdu"], ["fa", "Persian"], ["he", "Hebrew"], ["th", "Thai"],
  ["vi", "Vietnamese"], ["ms", "Malay"], ["fil", "Filipino"], ["sw", "Swahili"],
  ["af", "Afrikaans"], ["nb", "Norwegian Bokmål"],
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
  align: boolean
  escalate: boolean
  repair: boolean
  pages: string
}

// Beginner defaults: keep the original format, auto-detect source, auto layout/OCR/engine.
const DEFAULTS: FormValues = {
  target_lang: "id", source_lang: "auto", output_format: "same-as-source", engine: "fallback",
  fidelity: "auto", layout: "auto", ocr_engine: "auto", register: "auto",
  bilingual: false, quality: true, localize: false, align: true, escalate: false, repair: false, pages: "",
}

function fmtSize(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
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
  onSubmit: (files: File[], v: FormValues) => void
}) {
  const { t } = useI18n()
  const [v, setV] = useState<FormValues>(DEFAULTS)
  const [files, setFiles] = useState<File[]>([])
  const [drag, setDrag] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const set = <K extends keyof FormValues>(k: K, val: FormValues[K]) => setV((p) => ({ ...p, [k]: val }))

  const FORMATS = health?.formats ?? ["same-as-source", "pdf", "docx", "markdown"]

  return (
    <Card>
      <CardContent className="space-y-5 pt-5">
        {/* Drop zone — a real button so it's keyboard-reachable (Tab) and operable (Enter/Space),
            not a mouse-only <div onClick>. */}
        <div
          role="button"
          tabIndex={0}
          aria-label={t("drop_doc")}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); inputRef.current?.click() } }}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files.length) setFiles(Array.from(e.dataTransfer.files)) }}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-primary ${drag ? "border-primary bg-accent" : "border-border"}`}
        >
          <FileUp className={`h-8 w-8 ${drag ? "text-primary" : "text-muted-foreground"}`} aria-hidden />
          <div className="text-sm">
            {files.length ? <span className="font-medium">{files.length === 1 ? t("file_one") : `${files.length} files`} {t("files_selected")}</span>
              : <><span className="font-medium text-foreground">{t("drop_doc")}</span> {t("or_browse")}</>}
          </div>
          <p className="text-xs text-muted-foreground">
            {t("filetypes")}
          </p>
          <input ref={inputRef} type="file" multiple className="hidden"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
        </div>

        {/* selected files: name + size + remove */}
        {files.length > 0 && (
          <ul className="space-y-1.5">
            {files.map((f, i) => (
              <li key={`${f.name}-${i}`}
                className="flex items-center gap-2 rounded-md border bg-muted/30 px-3 py-2 text-sm">
                <FileUp className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                <span className="shrink-0 tabular-nums text-xs text-muted-foreground">{fmtSize(f.size)}</span>
                <button type="button" aria-label={`Remove ${f.name}`}
                  onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))}
                  className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground">
                  <X className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* The two things a beginner actually chooses */}
        <div className="grid grid-cols-2 gap-4">
          <Field label={t("f_translate_to")}>
            <Picker value={v.target_lang} onChange={(x) => set("target_lang", x)}
              options={LANGS.map((l) => l[0])} labels={Object.fromEntries(LANGS)} />
          </Field>
          <Field label={t("f_output")}>
            <Picker value={v.output_format} onChange={(x) => set("output_format", x)}
              options={FORMATS}
              labels={{ "same-as-source": t("opt_same") }} />
          </Field>
        </div>

        <Button disabled={!files.length || busy} className="w-full" size="lg"
          onClick={() => files.length && onSubmit(files, v)}>
          {busy ? <><Loader2 className="h-4 w-4 animate-spin" /> {t("working")}</>
            : files.length > 1 ? `${t("translate")} ${files.length}` : t("translate")}
        </Button>

        {/* Advanced — hidden by default */}
        <div>
          <button type="button" onClick={() => setAdvanced((a) => !a)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <Settings2 className="h-4 w-4" /> {t("advanced")}
            <ChevronDown className={`h-4 w-4 transition-transform ${advanced ? "rotate-180" : ""}`} />
          </button>

          {advanced && (
            <div className="mt-4 space-y-4 rounded-lg border bg-muted/20 p-4">
              <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
                <Field label={t("f_source")}>
                  <Picker value={v.source_lang} onChange={(x) => set("source_lang", x)}
                    options={["auto", ...LANGS.map((l) => l[0])]}
                    labels={{ auto: t("opt_auto"), ...Object.fromEntries(LANGS) }} />
                </Field>
                <Field label={t("f_engine")} hint={t("hint_engine")}>
                  <Picker value={v.engine} onChange={(x) => set("engine", x)}
                    options={health?.engines ?? ["fallback"]} />
                </Field>
                <Field label={t("f_fidelity")}>
                  <Picker value={v.fidelity} onChange={(x) => set("fidelity", x)}
                    options={health?.fidelity ?? ["auto"]} />
                </Field>
                <Field label={t("f_layout")} hint={t("hint_layout")}>
                  <Picker value={v.layout} onChange={(x) => set("layout", x)}
                    options={health?.layout ?? ["auto", "off", "paddle"]} />
                </Field>
                <Field label={t("f_ocr")}>
                  <Picker value={v.ocr_engine} onChange={(x) => set("ocr_engine", x)}
                    options={health?.ocr ?? ["auto"]} />
                </Field>
                <Field label={t("f_register")}>
                  <Picker value={v.register} onChange={(x) => set("register", x)}
                    options={health?.register ?? ["auto"]} />
                </Field>
                <Field label={t("f_pages")} hint='e.g. "3-7,10"'>
                  <input value={v.pages} onChange={(e) => set("pages", e.target.value)}
                    placeholder={t("ph_all")}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
                </Field>
              </div>
              <div className="flex flex-wrap gap-6">
                {([["bilingual", "tog_bilingual"], ["quality", "tog_quality"], ["localize", "tog_localize"], ["align", "tog_align"], ["escalate", "tog_escalate"], ["repair", "tog_repair"]] as const).map(
                  ([k, key]) => (
                    <label key={k} className="flex items-center gap-2 text-sm">
                      <Switch checked={v[k]} onCheckedChange={(c) => set(k, c)} />
                      {t(key)}
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
