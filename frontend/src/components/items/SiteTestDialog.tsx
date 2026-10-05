import { useState } from 'react'
import { post } from '@/api/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'

type Result = { state: string; status_code: number | null; detail?: string }

export function SiteTestDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const [busy, setBusy] = useState(false)
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent>
    <DialogHeader><DialogTitle>Test a site</DialogTitle><DialogDescription>Checks whether the tracker can reach a public URL now. A reachable result does not guarantee future checks.</DialogDescription></DialogHeader>
    <form className="space-y-3" onSubmit={async (event) => {
      event.preventDefault(); setBusy(true); setResult(null)
      try { setResult(await post<Result>('/tools/site-test', { url })) }
      catch (error) { setResult({ state: 'INCONCLUSIVE', status_code: null, detail: error instanceof Error ? error.message : 'Test failed' }) }
      finally { setBusy(false) }
    }}>
      <Input type="url" aria-label="Site URL" placeholder="https://example.com/series" value={url} onChange={(event) => setUrl(event.target.value)} required />
      <Button type="submit" disabled={busy}>{busy ? 'Testing…' : 'Test URL'}</Button>
      {result && <p role="status" className="text-sm">{result.state.replaceAll('_', ' ')}{result.status_code ? ` · HTTP ${result.status_code}` : ''}{result.detail ? ` · ${result.detail}` : ''}</p>}
    </form>
  </DialogContent></Dialog>
}
