import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { post } from '@/api/client'
import type { TocExtractionPreview } from '@/types/api'

interface Props {
  tocUrl: string
  exampleUrls: string[]
  setExampleUrls: (value: string[]) => void
  rowHtml: string
  setRowHtml: (value: string) => void
  preferredGroup: string
  setPreferredGroup: (value: string) => void
  onApply?: (result: TocExtractionPreview) => void
}

export function TocExtractionPanel({
  tocUrl, exampleUrls, setExampleUrls, rowHtml, setRowHtml,
  preferredGroup, setPreferredGroup, onApply,
}: Props) {
  const [preview, setPreview] = useState<TocExtractionPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function test() {
    setBusy(true)
    setError('')
    setPreview(null)
    try {
      const result = await post<TocExtractionPreview>('/tools/toc-preview', {
        url: tocUrl.trim(),
        example_urls: exampleUrls.map((url) => url.trim()).filter(Boolean),
        row_html: rowHtml.trim() || null,
        preferred_group: preferredGroup || null,
      })
      setPreview(result)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'ToC test failed.')
    } finally {
      setBusy(false)
    }
  }

  return <div className="space-y-3 rounded-md border border-border p-3 text-xs">
    <div className="font-medium">Test ToC extraction</div>
    <p className="text-muted-foreground">Reads the series page and previews real chapter links. A reachable site may still have no chapter links in its HTML.</p>
    {[0, 1].map((index) => <div key={index} className="space-y-1">
      <Label htmlFor={`toc-example-${index}`}>Example chapter link {index + 1} (optional)</Label>
      <Input id={`toc-example-${index}`} type="url" value={exampleUrls[index] ?? ''}
        placeholder="https://example.com/series/chapter-63"
        onChange={(event) => setExampleUrls([0, 1].map((slot) => slot === index ? event.target.value : exampleUrls[slot] ?? ''))} />
    </div>)}
    <div className="space-y-1">
      <Label htmlFor="toc-row-html">Copied chapter row HTML (optional)</Label>
      <textarea id="toc-row-html" rows={2} maxLength={5000} value={rowHtml}
        onChange={(event) => setRowHtml(event.target.value)}
        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
        placeholder="<li class=&quot;chapter-row&quot;>…</li>" />
      <p className="text-muted-foreground">Used only to identify a row class. The HTML itself is not saved.</p>
    </div>
    <Button type="button" size="sm" variant="outline" disabled={!tocUrl.trim() || busy} onClick={test}>
      {busy ? 'Checking…' : 'Test ToC extraction'}
    </Button>
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {preview && <div className="space-y-2 rounded border border-border bg-muted/30 p-2">
      <p><strong>{preview.state}</strong> · {preview.method} · {preview.confidence ?? 'LOW'} confidence</p>
      {preview.latest_chapter && <p>Latest: <a className="break-all hover:text-primary hover:underline" href={preview.latest_url ?? undefined} target="_blank" rel="noopener noreferrer">chapter {preview.latest_chapter}</a></p>}
      {preview.groups && preview.groups.length > 0 && <div className="space-y-1">
        <Label htmlFor="preferred-group">Preferred group for reading links</Label>
        <select id="preferred-group" value={preferredGroup} onChange={(event) => setPreferredGroup(event.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2">
          <option value="">Any group</option>
          {preview.groups.map((group) => <option key={group} value={group}>{preview.group_labels?.[group] ?? group}</option>)}
        </select>
        <p className="text-muted-foreground">All groups still count toward the latest chapter.</p>
      </div>}
      {preview.samples && preview.samples.length > 0 && <div>
        <p className="font-medium">Matched links</p>
        <ul className="space-y-1">{preview.samples.map((sample) => <li key={sample.url} className="break-all">
          {sample.chapter}{sample.group ? ` · group ${sample.group}` : ''} · <a href={sample.url} target="_blank" rel="noopener noreferrer" className="hover:text-primary hover:underline">{sample.url}</a>
        </li>)}</ul>
      </div>}
      {preview.warnings.map((warning) => <p key={warning} className="text-amber-500">{warning}</p>)}
      {onApply && preview.state === 'OK' && <Button type="button" size="sm" variant="outline" onClick={() => onApply(preview)}>Use found details</Button>}
    </div>}
  </div>
}
