import { useEffect, useRef, useState } from 'react'
import { Loader2, Sparkles, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useCreateItem } from '@/hooks/useItems'
import { usePatternDetect } from '@/hooks/usePatternDetect'
import { toast } from 'sonner'
import type { PatternDetectionResult } from '@/types/api'

interface AddItemDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CONFIDENCE_VARIANT = {
  HIGH: 'success',
  MEDIUM: 'warning',
  LOW: 'destructive',
} as const

export function AddItemDialog({ open, onOpenChange }: AddItemDialogProps) {
  const [step, setStep] = useState<1 | 2>(1)
  const [url, setUrl] = useState('')
  const [manualRegex, setManualRegex] = useState('')
  const [title, setTitle] = useState('')
  const [interval, setInterval] = useState('60')
  const [preview, setPreview] = useState<PatternDetectionResult | null>(null)

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const detect = usePatternDetect()
  const create = useCreateItem()

  // Reset on close
  useEffect(() => {
    if (!open) {
      setStep(1)
      setUrl('')
      setManualRegex('')
      setTitle('')
      setInterval('60')
      setPreview(null)
    }
  }, [open])

  // Debounced pattern preview
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!url.trim()) { setPreview(null); return }
    debounceRef.current = setTimeout(() => {
      detect.mutate(
        { url: url.trim(), manual_regex: manualRegex.trim() || null },
        { onSuccess: setPreview, onError: () => setPreview(null) },
      )
    }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, manualRegex])

  function handleNext() {
    if (!url.trim()) return
    setStep(2)
  }

  function handleSubmit() {
    create.mutate(
      {
        url: url.trim(),
        title: title.trim() || null,
        manual_regex: manualRegex.trim() || null,
        check_interval_min: parseInt(interval) || 60,
      },
      {
        onSuccess: () => {
          toast.success('Item added.')
          onOpenChange(false)
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{step === 1 ? 'Add tracked item' : 'Confirm details'}</DialogTitle>
          <DialogDescription>
            {step === 1
              ? 'Paste the URL of a specific chapter or episode — we\'ll detect the pattern automatically.'
              : 'Review the detected pattern and optionally add a title.'}
          </DialogDescription>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            {/* URL input */}
            <div className="space-y-1.5">
              <Label htmlFor="url">URL</Label>
              <Input
                id="url"
                placeholder="https://example.com/novel/chapter-183"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                autoFocus
              />
            </div>

            {/* Manual regex */}
            <div className="space-y-1.5">
              <Label htmlFor="regex">
                Custom regex{' '}
                <span className="text-muted-foreground font-normal">(optional · one capture group)</span>
              </Label>
              <Input
                id="regex"
                placeholder="chapter-(\d+)"
                value={manualRegex}
                onChange={(e) => setManualRegex(e.target.value)}
                className="font-mono text-xs"
              />
            </div>

            {/* Pattern preview */}
            {(detect.isPending) && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Detecting pattern…
              </div>
            )}
            {preview && (
              <div className="rounded-lg border border-border bg-muted/30 p-3 space-y-2 text-xs">
                <div className="flex items-center gap-2 font-medium">
                  <Sparkles className="h-3.5 w-3.5 text-primary" />
                  Pattern detected
                  <Badge variant={CONFIDENCE_VARIANT[preview.confidence]} className="ml-auto text-[10px]">
                    {preview.confidence}
                  </Badge>
                  <Badge variant="outline" className="text-[10px]">{preview.strategy_used}</Badge>
                </div>
                {preview.url_template && (
                  <div className="space-y-0.5">
                    <span className="text-muted-foreground">Template</span>
                    <p className="font-mono break-all text-foreground">{preview.url_template}</p>
                  </div>
                )}
                <div className="flex gap-4">
                  {preview.current_chapter && (
                    <div>
                      <span className="text-muted-foreground">Starting chapter  </span>
                      <span className="font-semibold">{preview.current_chapter}</span>
                    </div>
                  )}
                  {preview.chapter_regex && (
                    <div>
                      <span className="text-muted-foreground">Regex  </span>
                      <code className="font-mono">{preview.chapter_regex}</code>
                    </div>
                  )}
                </div>
                {!preview.url_template && (
                  <div className="flex items-center gap-1.5 text-destructive">
                    <AlertCircle className="h-3.5 w-3.5" />
                    Could not detect a pattern. You can still add the item and override the regex later.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            {/* Title */}
            <div className="space-y-1.5">
              <Label htmlFor="title">
                Title <span className="text-muted-foreground font-normal">(optional)</span>
              </Label>
              <Input
                id="title"
                placeholder={url ? new URL(url).hostname : 'My Novel'}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                autoFocus
              />
            </div>

            {/* Check interval */}
            <div className="space-y-1.5">
              <Label htmlFor="interval">Check interval (minutes)</Label>
              <Input
                id="interval"
                type="number"
                min="5"
                max="10080"
                value={interval}
                onChange={(e) => setInterval(e.target.value)}
              />
            </div>

            {/* Summary */}
            {preview?.url_template && (
              <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs space-y-1 font-mono break-all text-muted-foreground">
                {preview.url_template}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {step === 2 && (
            <Button variant="outline" onClick={() => setStep(1)}>
              Back
            </Button>
          )}
          {step === 1 ? (
            <Button onClick={handleNext} disabled={!url.trim()}>
              Next
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={create.isPending}>
              {create.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Add item
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
