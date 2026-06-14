import { ChevronLeft, ChevronRight, Download } from "lucide-react"
import { useEffect, useState } from "react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { downloadUrl, getPreviewInfo, type PreviewInfo, previewUrl } from "@/lib/api"

function Pane({ title, jid, which, page, ok, pages }: {
  title: string; jid: string; which: "source" | "output"; page: number
  ok: boolean; pages: number
}) {
  return (
    <div className="flex-1 space-y-2">
      <div className="text-xs font-medium text-muted-foreground">
        {title} {ok && <span>· {pages} pages</span>}
      </div>
      <div className="flex min-h-[300px] items-center justify-center overflow-hidden rounded-md border bg-muted/30">
        {ok && page < pages ? (
          <img src={previewUrl(jid, which, page)} alt={`${which} p${page + 1}`}
            className="max-h-[70vh] w-full object-contain" />
        ) : (
          <span className="p-8 text-center text-sm text-muted-foreground">
            No image preview for this format — use the download button.
          </span>
        )}
      </div>
    </div>
  )
}

export function PreviewPanel({ jid }: { jid: string }) {
  const [info, setInfo] = useState<PreviewInfo | null>(null)
  const [page, setPage] = useState(0)

  useEffect(() => {
    setPage(0)
    getPreviewInfo(jid).then(setInfo).catch(() => setInfo(null))
  }, [jid])

  if (!info || (!info.source.ok && !info.output.ok)) return null
  const maxPages = Math.max(info.source.pages, info.output.pages, 1)

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Before & after</CardTitle>
        <div className="flex items-center gap-2">
          {maxPages > 1 && (
            <>
              <Button size="icon" variant="outline" disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}>
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="min-w-16 text-center text-sm tabular-nums">
                {page + 1} / {maxPages}
              </span>
              <Button size="icon" variant="outline" disabled={page >= maxPages - 1}
                onClick={() => setPage((p) => Math.min(maxPages - 1, p + 1))}>
                <ChevronRight className="h-4 w-4" />
              </Button>
            </>
          )}
          <a href={downloadUrl(jid)}>
            <Button size="sm"><Download className="h-4 w-4" /> Download</Button>
          </a>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 md:flex-row">
        <Pane title="Original" jid={jid} which="source" page={page}
          ok={info.source.ok} pages={info.source.pages} />
        <Pane title="Translated" jid={jid} which="output" page={page}
          ok={info.output.ok} pages={info.output.pages} />
      </CardContent>
    </Card>
  )
}
