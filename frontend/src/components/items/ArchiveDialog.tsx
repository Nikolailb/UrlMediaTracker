import { useState } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { postBlob, postFile } from '@/api/client'
import { useQueryClient } from '@tanstack/react-query'

export function ArchiveDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const [password, setPassword] = useState('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const qc = useQueryClient()
  async function download() {
    setBusy(true); setMessage('')
    try {
      const blob = await postBlob('/archive/export', { password })
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url; link.download = 'tracker-account.zip'; link.click()
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
      setPassword(''); setMessage('Full archive downloaded. It includes sensitive entries and covers.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Export failed.') }
    finally { setBusy(false) }
  }
  async function upload(file: File) {
    setBusy(true); setMessage('')
    try {
      const result = await postFile<{ created: number; skipped: number }>('/archive/import', file)
      qc.invalidateQueries({ queryKey: ['items'] })
      setMessage(`Imported ${result.created} entries; skipped ${result.skipped} duplicates.`)
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Import failed.') }
    finally { setBusy(false) }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent>
    <DialogHeader><DialogTitle>Portable account archive</DialogTitle><DialogDescription>A full ZIP includes every entry, including sensitive entries and covers. Keep it somewhere private.</DialogDescription></DialogHeader>
    <div className="space-y-3">
      <label className="block text-sm">Confirm your password<Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></label>
      <Button disabled={!password || busy} onClick={download}>Download full ZIP</Button>
      <label className="block text-sm">Import ZIP to this library<Input type="file" accept=".zip,application/zip" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) upload(file); e.target.value = '' }} /></label>
      {message && <p role="status" className="text-sm">{message}</p>}
    </div>
  </DialogContent></Dialog>
}
