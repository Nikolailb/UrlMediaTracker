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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { PatternDetectionResult } from '@/types/api'
import { ITEM_CATEGORIES } from '@/types/api'
import { post } from '@/api/client'
import { itemsApi } from '@/api/items'
import { useQueryClient } from '@tanstack/react-query'
import { TocExtractionPanel } from './TocExtractionPanel'
import { useAuth } from '@/auth/context'

type SourcePreview = { title: string | null; current_chapter: string | null; latest_chapter: string | null; cover_url: string | null; checker: string; access: { state: string; status_code: number | null } }

interface AddItemDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const CONFIDENCE_VARIANT = {
  HIGH: 'success',
  MEDIUM: 'warning',
  LOW: 'destructive',
} as const

const NOVEL_CHECKERS = new Set(['FREEWEBNOVEL', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'])

export function AddItemDialog({ open, onOpenChange }: AddItemDialogProps) {
  const [step, setStep] = useState<1 | 2>(1)
  const [url, setUrl] = useState('')
  const [manualRegex, setManualRegex] = useState('')
  const [chapterExampleUrl, setChapterExampleUrl] = useState('')
  const [strategyOverride, setStrategyOverride] = useState('AUTO')
  const [title, setTitle] = useState('')
  const [interval, setInterval] = useState('360')
  const [tocUrl, setTocUrl] = useState('')
  const [category, setCategory] = useState('')
  const [preview, setPreview] = useState<PatternDetectionResult | null>(null)
  const [sourcePreview, setSourcePreview] = useState<SourcePreview | null>(null)
  const [previewPending, setPreviewPending] = useState(false)
  const [previewError, setPreviewError] = useState(false)
  const [note, setNote] = useState('')
  const [sensitive, setSensitive] = useState(false)
  const [currentChapter, setCurrentChapter] = useState('')
  const [latestChapter, setLatestChapter] = useState('')
  const [coverUrl, setCoverUrl] = useState('')
  const [tocExamples, setTocExamples] = useState<string[]>(['', ''])
  const [tocRowHtml, setTocRowHtml] = useState('')
  const [preferredGroup, setPreferredGroup] = useState('')

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const categoryEdited = useRef(false)
  const detect = usePatternDetect()
  const create = useCreateItem()
  const queryClient = useQueryClient()
  const { session } = useAuth()

  // Reset on close
  useEffect(() => {
    if (!open) {
      setStep(1)
      setUrl('')
      setManualRegex('')
      setChapterExampleUrl('')
      setStrategyOverride('AUTO')
      setTitle('')
      setInterval('360')
      setTocUrl('')
      setCategory('')
      categoryEdited.current = false
      setPreview(null)
      setSourcePreview(null)
      setPreviewError(false)
      setNote('')
      setSensitive(false)
      setCurrentChapter('')
      setLatestChapter('')
      setCoverUrl('')
      setTocExamples(['', ''])
      setTocRowHtml('')
      setPreferredGroup('')
    }
  }, [open])

  // REQ-004: chapter pattern detection is advisory, never a series-URL gate.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!url.trim() || step !== 2) { setPreview(null); return }
    debounceRef.current = setTimeout(() => {
      detect.mutate(
        { url: chapterExampleUrl.trim() || url.trim(), manual_regex: manualRegex.trim() || null },
        { onSuccess: setPreview, onError: () => setPreview(null) },
      )
    }, 400)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, chapterExampleUrl, manualRegex, step])

  async function handleNext() {
    if (!url.trim()) return
    setSourcePreview(null)
    setPreviewError(false)
    setStep(2)
    setPreviewPending(true)
    try {
      const result = await post<SourcePreview>('/tools/preview', { url: url.trim() })
      setSourcePreview(result)
      if (!categoryEdited.current) setCategory(NOVEL_CHECKERS.has(result.checker) ? 'Novel' : '')
    } catch {
      setSourcePreview(null)
      setPreviewError(true)
    } finally {
      setPreviewPending(false)
    }
  }

  function useDetectedDetails() {
    if (!sourcePreview) return
    if (sourcePreview.title) setTitle(sourcePreview.title)
    if (sourcePreview.current_chapter) setCurrentChapter(sourcePreview.current_chapter)
    if (sourcePreview.latest_chapter) setLatestChapter(sourcePreview.latest_chapter)
    if (sourcePreview.cover_url) setCoverUrl(sourcePreview.cover_url)
  }

  function handleSubmit() {
    create.mutate(
      {
        url: url.trim(),
        chapter_url: chapterExampleUrl.trim() || null,
        title: title.trim() || null,
        manual_regex: manualRegex.trim() || null,
        strategy_override: strategyOverride === 'AUTO' ? null : strategyOverride,
        check_interval_min: parseInt(interval) || 360,
        toc_url: tocUrl.trim() || (chapterExampleUrl.trim() ? url.trim() : null),
        category: category || (categoryEdited.current ? null : undefined),
        note: note.trim() || null,
        is_sensitive: sensitive,
        current_chapter: currentChapter.trim() || null,
        latest_chapter: latestChapter.trim() || null,
        preferred_group: preferredGroup || null,
        toc_example_urls: tocExamples.map((entry) => entry.trim()).filter(Boolean),
        toc_row_html: tocRowHtml.trim() || null,
      },
      {
        onSuccess: async (created) => {
          if (sensitive && session?.safe_view_enabled) {
            toast.success('Sensitive item added. Reveal sensitive entries to see it in your library.')
            if (coverUrl.trim() && !created.cover_filename) {
              toast.warning('Reveal the item before setting its custom cover URL.')
            }
            onOpenChange(false)
            return
          }
          if (coverUrl.trim()) {
            try {
              await itemsApi.setCoverUrl(created.id, coverUrl.trim())
              await queryClient.invalidateQueries({ queryKey: ['items'] })
              toast.success('Item and cover added.')
            } catch (error) {
              toast.warning(`Item added, but cover could not be fetched: ${error instanceof Error ? error.message : 'unknown error'}`)
            }
          } else toast.success('Item added.')
          onOpenChange(false)
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{step === 1 ? 'Add tracked item' : 'Confirm details'}</DialogTitle>
          <DialogDescription>
            {step === 1
              ? 'Paste a series or chapter URL. We will check the source before you save it.'
              : 'Review the source, use detected details if they look right, then set your reading position.'}
          </DialogDescription>
        </DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="url">URL</Label>
              <Input
                id="url"
                placeholder="https://example.com/novel/my-series"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                autoFocus
              />
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-4">
            {previewPending && <p className="text-sm text-muted-foreground">Checking source…</p>}
            {previewError && <p className="text-sm text-amber-600">The source preview could not be completed. You can still enter details and track it manually.</p>}
            {sourcePreview && <div className="rounded-lg border p-3 text-xs space-y-2">
              <p>Source: <strong>{sourcePreview.access.state.replaceAll('_', ' ')}</strong>{sourcePreview.access.status_code ? ` (HTTP ${sourcePreview.access.status_code})` : ''}</p>
              <p>Suggested checker: <strong>{sourcePreview.checker}</strong></p>
              {sourcePreview.title && <p>Title found: {sourcePreview.title}</p>}
              {sourcePreview.latest_chapter && <p>Latest found: chapter {sourcePreview.latest_chapter}</p>}
              {sourcePreview.current_chapter && <p>Chapter in URL: {sourcePreview.current_chapter}</p>}
              {sourcePreview.cover_url && <img src={sourcePreview.cover_url} alt="Detected cover preview" className="h-20 max-w-20 object-cover rounded" />}
              {(sourcePreview.title || sourcePreview.latest_chapter || sourcePreview.current_chapter || sourcePreview.cover_url) &&
                <Button type="button" size="sm" variant="outline" onClick={useDetectedDetails}>Use detected details</Button>}
              {!['REACHABLE', 'REACHABLE_VIA_BROWSER'].includes(sourcePreview.access.state) && <p className="text-amber-600">Automatic checking may fail. You can still track this manually.</p>}
            </div>}
            <div className="space-y-1.5">
              <Label htmlFor="title">Title <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Input id="title" placeholder="Series title" value={title} onChange={(e) => setTitle(e.target.value)} autoFocus />
            </div>
            <div className="space-y-1.5"><Label htmlFor="add-current">Your current chapter</Label><Input id="add-current" value={currentChapter} onChange={(e) => setCurrentChapter(e.target.value)} placeholder="Leave blank if you have not started" /></div>
            <div className="space-y-1.5"><Label htmlFor="add-latest">Latest chapter</Label><Input id="add-latest" value={latestChapter} onChange={(e) => setLatestChapter(e.target.value)} placeholder="Optional; use detected details or enter manually" /></div>
            <div className="space-y-1.5">
              <Label htmlFor="interval">Check interval (minutes)</Label>
              <Input id="interval" type="number" min="5" max="10080" value={interval} onChange={(e) => setInterval(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="category">Category <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Select value={category} onValueChange={(v) => { categoryEdited.current = true; setCategory(v === '__none__' ? '' : v) }}>
                <SelectTrigger id="category"><SelectValue placeholder="No category" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none__">No category</SelectItem>
                  {ITEM_CATEGORIES.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5"><Label htmlFor="add-note">Personal note (optional)</Label><Input id="add-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
            <div className="space-y-1.5"><Label htmlFor="add-cover-url">Cover image URL (optional)</Label><Input id="add-cover-url" type="url" placeholder="https://example.com/cover.jpg" value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)} /></div>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={sensitive} onChange={(e) => setSensitive(e.target.checked)} /> Sensitive entry</label>

            <details className="rounded-lg border border-border p-3 text-sm">
              <summary className="cursor-pointer font-medium">Advanced checking options</summary>
              <div className="space-y-4 pt-3">
                <div className="space-y-1.5">
                  <Label htmlFor="chapter-example-url">Chapter URL example (optional)</Label>
                  <Input id="chapter-example-url" type="url" placeholder="https://example.com/my-series-chapter-55/" value={chapterExampleUrl} onChange={(e) => setChapterExampleUrl(e.target.value)} />
                  <p className="text-xs text-muted-foreground">Use this when the first URL is a series or ToC page. It defines chapter links; chapter 55 here will not be saved as your progress or the latest chapter.</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="toc-url">Table of contents URL (optional)</Label>
                  <Input id="toc-url" placeholder="https://example.com/series/chapters" value={tocUrl} onChange={(e) => setTocUrl(e.target.value)} />
                  <p className="text-xs text-muted-foreground">With a chapter URL example, the first URL is used as the ToC by default. Enter a different ToC here only if needed.</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="add-strategy">Checking strategy</Label>
                  <Select value={strategyOverride} onValueChange={setStrategyOverride}>
                    <SelectTrigger id="add-strategy"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="AUTO">Automatic (recommended)</SelectItem>
                      {sourcePreview?.checker === 'FREEWEBNOVEL' && <SelectItem value="FREEWEBNOVEL">FreeWebNovel site checker</SelectItem>}
                      {sourcePreview?.checker === 'COMIX' && <SelectItem value="COMIX">Comix site checker</SelectItem>}
                      {sourcePreview?.checker === 'WEBNOVEL' && <SelectItem value="WEBNOVEL">WebNovel site checker</SelectItem>}
                      {sourcePreview?.checker === 'ROYALROAD' && <SelectItem value="ROYALROAD">Royal Road site checker</SelectItem>}
                      {sourcePreview?.checker === 'SCRIBBLEHUB' && <SelectItem value="SCRIBBLEHUB">Scribble Hub site checker</SelectItem>}
                      <SelectItem value="TOC_SCRAPER">Table of contents scan</SelectItem>
                      <SelectItem value="INCREMENTAL_PROBE">Sequential URL probing</SelectItem>
                      <SelectItem value="TOC_THEN_PROBE">ToC, then probe if unsupported</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">ToC scans read actual chapter links and need a ToC URL. Sequential probing needs a predictable chapter URL pattern. Automatic prefers a dedicated site checker.</p>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="regex">Chapter URL regex (optional · one capture group)</Label>
                  <Input id="regex" placeholder="chapter-(\d+)" value={manualRegex} onChange={(e) => setManualRegex(e.target.value)} className="font-mono text-xs" />
                  <p className="text-xs text-muted-foreground">Use only when the chapter URL pattern needs an override. A series page does not need a regex for a dedicated site checker.</p>
                </div>
            {['FREEWEBNOVEL', 'COMIX', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'].includes(sourcePreview?.checker ?? '') && strategyOverride === 'AUTO' && <p className="text-xs text-muted-foreground">The dedicated checker needs no chapter URL regex.</p>}
            {(!['FREEWEBNOVEL', 'COMIX', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'].includes(sourcePreview?.checker ?? '') || !['AUTO', 'FREEWEBNOVEL', 'COMIX', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'].includes(strategyOverride)) && detect.isPending && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Detecting pattern…
              </div>
            )}
            {(!['FREEWEBNOVEL', 'COMIX', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'].includes(sourcePreview?.checker ?? '') || !['AUTO', 'FREEWEBNOVEL', 'COMIX', 'WEBNOVEL', 'ROYALROAD', 'SCRIBBLEHUB'].includes(strategyOverride)) && preview && (
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
                      <span className="text-muted-foreground">{chapterExampleUrl.trim() ? 'Example chapter  ' : 'Chapter in URL  '}</span>
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
                    {['opaque_id', 'ambiguous_id'].includes(preview.strategy_used)
                      ? 'This chapter URL has another numeric ID. Sequential probing cannot predict future links; a ToC scan can use your regex and actual links.'
                      : 'No reusable URL pattern found. Try a ToC extraction test or track manually.'}
                  </div>
                )}
              </div>
            )}
              </div>
              <TocExtractionPanel key={`${strategyOverride}:${tocUrl.trim() || url.trim()}:${chapterExampleUrl}:${manualRegex}`} tocUrl={tocUrl.trim() || url.trim()} chapterExampleUrl={chapterExampleUrl} strategyOverride={strategyOverride} chapterRegex={manualRegex} onStrategyChange={setStrategyOverride} exampleUrls={tocExamples}
                setExampleUrls={setTocExamples} rowHtml={tocRowHtml} setRowHtml={setTocRowHtml}
                preferredGroup={preferredGroup} setPreferredGroup={setPreferredGroup}
                onApply={(found) => {
                  if (found.title) setTitle(found.title)
                  if (found.latest_chapter) setLatestChapter(found.latest_chapter)
                  if (found.cover_url) setCoverUrl(found.cover_url)
                }} />
            </details>
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
