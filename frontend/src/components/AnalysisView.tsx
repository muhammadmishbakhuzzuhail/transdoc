// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { Download, FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { type Analysis, downloadUrl, reportUrl } from "@/lib/api"
import { useI18n } from "@/lib/i18n"

function Stat({ label, value, alert }: { label: string; value: React.ReactNode; alert?: boolean }) {
  return (
    <div className="rounded-md border p-3">
      <div className={`text-2xl font-semibold ${alert ? "text-destructive" : ""}`}>{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b py-1.5 text-sm last:border-0">
      <span className="text-muted-foreground">{k}</span>
      <span className="text-right font-medium">{v}</span>
    </div>
  )
}

export function AnalysisView({ jid, a }: { jid: string; a: Analysis }) {
  const { t } = useI18n()
  const p = a.profile
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>{t("an_title")}</CardTitle>
        <div className="flex gap-2">
          <a href={downloadUrl(jid)}>
            <Button size="sm"><Download className="h-4 w-4" /> {t("btn_download")}</Button>
          </a>
          <a href={reportUrl(jid)} target="_blank" rel="noreferrer">
            <Button size="sm" variant="outline"><FileText className="h-4 w-4" /> {t("btn_report")}</Button>
          </a>
        </div>
      </CardHeader>
      <CardContent>
        <div className="mb-5 grid grid-cols-3 gap-3 md:grid-cols-6">
          <Stat label={t("st_pages")} value={a.counts.pages} />
          <Stat label={t("st_blocks")} value={a.counts.blocks} />
          <Stat label={t("st_flagged")} value={a.counts.flagged} alert={a.counts.flagged > 0} />
          <Stat label={t("st_crops")} value={a.layout.crops} />
          <Stat label={t("st_illegible")} value={a.rendering.illegible} alert={a.rendering.illegible > 0} />
          <Stat label={t("st_repairs")} value={a.repairs.length} />
        </div>

        <Tabs defaultValue="profile">
          <TabsList>
            <TabsTrigger value="profile">{t("tab_profile")}</TabsTrigger>
            <TabsTrigger value="flagged">{t("tab_flagged")} ({a.flagged.length})</TabsTrigger>
            <TabsTrigger value="glossary">{t("tab_glossary")} ({a.glossary.length})</TabsTrigger>
            <TabsTrigger value="repairs">{t("tab_repairs")} ({a.repairs.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="profile">
            <div className="space-y-1">
              <Row k={t("r_input_nature")} v={p.input_nature} />
              <Row k={t("r_damage")} v={p.damage_level} />
              <Row k={t("r_source_langs")} v={p.source_langs.join(", ") || "—"} />
              <Row k={t("r_target_lang")} v={p.target_lang} />
              <Row k={t("r_genre")} v={p.genre} />
              <Row k={t("r_reading_order")} v={p.reading_order} />
              <Row k={t("r_layout_model")} v={a.layout.enabled ? t("lay_on") : t("lay_off")} />
              <Row k={t("r_structure")} v={
                <div className="flex flex-wrap justify-end gap-1">
                  {p.structure.length ? p.structure.map((s, i) => <Badge key={i} variant="secondary">{s}</Badge>) : "—"}
                </div>
              } />
              {p.risk_flags.length > 0 && <Row k={t("r_risk_flags")} v={
                <div className="flex flex-wrap justify-end gap-1">
                  {p.risk_flags.map((s, i) => <Badge key={i} variant="destructive">{s}</Badge>)}
                </div>
              } />}
            </div>
          </TabsContent>

          <TabsContent value="flagged">
            {a.flagged.length === 0 ? <Empty msg={t("e_clean")} /> : (
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {a.flagged.map((f, i) => (
                  <div key={i} className="rounded-md border p-3 text-sm">
                    <div className="mb-1 flex items-center gap-2">
                      <Badge variant="outline">p{f.page}</Badge>
                      <Badge variant="secondary">{f.type}</Badge>
                      {Object.keys(f.flags).map((k) => <Badge key={k} variant="destructive">{k}</Badge>)}
                    </div>
                    <div className="text-muted-foreground">{f.text || "—"}</div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="glossary">
            {a.glossary.length === 0 ? <Empty msg={t("e_no_glossary")} /> : (
              <div className="max-h-96 space-y-1 overflow-y-auto pr-1">
                {a.glossary.map((g, i) => (
                  <Row key={i} k={g.term} v={<span><b>{g.rendering}</b> <span className="text-muted-foreground">({g.action})</span></span>} />
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="repairs">
            {a.repairs.length === 0 ? <Empty msg={t("e_no_repairs")} /> : (
              <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                {a.repairs.map((r, i) => (
                  <div key={i} className="rounded-md border p-3 text-sm">
                    <div className="text-xs text-muted-foreground">{r.reason}</div>
                    <div className="line-through opacity-60">{r.before}</div>
                    <div className="font-medium">{r.after}</div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  )
}

const Empty = ({ msg }: { msg: string }) => (
  <div className="py-8 text-center text-sm text-muted-foreground">{msg}</div>
)
