import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUpdateItem } from "@/hooks/useItems";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ItemRead } from "@/types/api";
import { ITEM_CATEGORIES } from "@/types/api";
import { cn } from "@/lib/utils";
import { itemsApi } from '@/api/items'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/auth/context'
import { usePatternDetect } from '@/hooks/usePatternDetect'
import { TocExtractionPanel } from './TocExtractionPanel'
import { hasAmbiguousChapterIds } from '@/lib/chapterUrls'

interface EditItemDialogProps {
  item: ItemRead | null;
  onOpenChange: (open: boolean) => void;
}

type Tab = "general" | "detection";

const STRATEGIES: {
  value: string;
  label: string;
  description: string;
}[] = [
  { value: 'AUTO', label: 'Automatic', description: 'Prefer a dedicated site checker when available.' },
  { value: 'COMIX', label: 'Comix site checker', description: 'Reads Comix series metadata and optional group links.' },
  { value: 'WEBNOVEL', label: 'WebNovel site checker', description: 'Reads WebNovel book catalog with optional browser fallback.' },
  { value: 'ROYALROAD', label: 'Royal Road site checker', description: 'Reads the fiction catalog by stable fiction ID.' },
  { value: 'SCRIBBLEHUB', label: 'Scribble Hub site checker', description: 'Reads the newest series ToC page and its explicit release order.' },
  {
    value: "INCREMENTAL_PROBE",
    label: "Sequential URL probing",
    description:
      "Builds chapter URLs from a template and probes them numerically.",
  },
  {
    value: "TOC_SCRAPER",
    label: "Table of contents scan",
    description: "Scrapes the ToC page for chapter links. Requires a ToC URL.",
  },
  {
    value: "TOC_THEN_PROBE",
    label: "ToC first, then probe",
    description:
      "Tries the ToC first; probes only when ToC checking is unsupported.",
  },
];

export function EditItemDialog({ item, onOpenChange }: EditItemDialogProps) {
  const open = item !== null;
  const [tab, setTab] = useState<Tab>("general");
  const [title, setTitle] = useState(item?.title ?? "");
  const [manualRegex, setManualRegex] = useState(item?.pattern_source === 'MANUAL' ? item.chapter_regex ?? '' : '');
  const [interval, setInterval] = useState(
    String(item?.check_interval_min ?? 360),
  );
  const [currentChapter, setCurrentChapter] = useState(
    item?.current_chapter ?? "",
  );
  const [isActive, setIsActive] = useState(item?.is_active ?? true);
  const [tocUrl, setTocUrl] = useState(item?.toc_url ?? "");
  const [chapterExampleUrl, setChapterExampleUrl] = useState("");
  const [tocExamples, setTocExamples] = useState<string[]>(item?.toc_example_urls ?? ['', '']);
  const [tocRowHtml, setTocRowHtml] = useState('');
  const [clearRowHint, setClearRowHint] = useState(false);
  const [preferredGroup, setPreferredGroup] = useState(item?.preferred_group ?? '');
  const [category, setCategory] = useState(item?.category ?? "");
  const [checkStrategy, setCheckStrategy] = useState<string>(
    item?.strategy_override ?? "AUTO",
  );
  const [note, setNote] = useState(item?.note ?? '')
  const [isSensitive, setIsSensitive] = useState(item?.is_sensitive ?? false)
  const [latestChapter, setLatestChapter] = useState(item?.latest_chapter ?? '')
  const [pendingDecision, setPendingDecision] = useState(item?.pending_latest_chapter ?? '')
  const [coverUrl, setCoverUrl] = useState('')
  const [coverFilename, setCoverFilename] = useState(item?.cover_filename ?? null)
  const [coverBusy, setCoverBusy] = useState(false)
  const qc = useQueryClient()
  const { selectedUser, session } = useAuth()

  const update = useUpdateItem();
  const patternPreview = usePatternDetect();

  async function handleSubmit() {
    if (!item) return;
    try {
      const saved = await update.mutateAsync({
        id: item.id,
        data: {
          title: title.trim() || null,
          chapter_url: chapterExampleUrl.trim() || undefined,
          manual_regex: manualRegex.trim() || null,
          check_interval_min: parseInt(interval) || 360,
          current_chapter: currentChapter.trim() || null,
          is_active: isActive,
          toc_url: tocUrl.trim() || null,
          category: category || null,
          strategy_override: checkStrategy === 'AUTO' ? null : checkStrategy,
          preferred_group: preferredGroup || null,
          toc_example_urls: tocExamples.map((entry) => entry.trim()).filter(Boolean),
          toc_row_html: tocRowHtml.trim() || (clearRowHint ? '' : undefined),
          note: note.trim() || null,
          is_sensitive: isSensitive,
          latest_chapter: (latestChapter.trim() || null) !== item.latest_chapter ? (latestChapter.trim() || null) : undefined,
        },
      });
      onOpenChange(false);
      if (saved.is_sensitive && session?.safe_view_enabled) {
        toast.success('Item saved and hidden by safe view. Reveal sensitive entries to see it.');
        return;
      }
      if (chapterExampleUrl.trim() && !saved.url_template && !saved.series_url) {
        toast.warning('No reusable chapter URL pattern was found. Use a working ToC scan or track manually.');
      }
      if (!saved.check_config_changed) {
        toast.success('Item updated. Checking method is unchanged.');
        return;
      }
      if (!saved.is_active) {
        toast.success('Checking settings saved. This item is paused.');
        return;
      }
      toast.info(`Checking settings saved. Testing ${saved.strategy_override ?? 'automatic'} now…`);
      try {
        const checked = await itemsApi.check(saved.id);
        await qc.invalidateQueries({ queryKey: ['items'] });
        if (checked.outcome === 'PENDING') toast.warning(`Check found chapter ${checked.pending_chapter}; review it before accepting.`);
        else if (checked.new_latest_chapter) toast.success(`Checker works. Found chapter ${checked.new_latest_chapter}.`);
        else if (checked.success) toast.success('Checker works. No new chapter.');
        else toast.warning(`Saved, but the new check failed: ${checked.error_message ?? checked.outcome ?? 'unknown issue'}`);
      } catch (error) {
        toast.warning(`Checking settings saved, but the check could not run: ${error instanceof Error ? error.message : 'unknown issue'}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save item.');
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col max-h-[calc(100dvh-4rem)]">
        <DialogHeader className="shrink-0">
          <DialogTitle>Edit item</DialogTitle>
          <DialogDescription>
            Update details for this tracked item.
          </DialogDescription>
        </DialogHeader>

        {/* Tab bar */}
        <div className="shrink-0 flex gap-1 border-b border-border -mx-6 px-6">
          {(["general", "detection"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-3 py-2 text-sm font-medium capitalize transition-colors",
                "border-b-2 -mb-px",
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Scrollable form body */}
        <div className="overflow-y-auto flex-1 -mx-6 px-6 py-4">
          {tab === "general" && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="edit-title">Title</Label>
                <Input
                  id="edit-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-chapter">Current chapter</Label>
                <Input
                  id="edit-chapter"
                  value={currentChapter}
                  onChange={(e) => setCurrentChapter(e.target.value)}
                  placeholder="e.g. 183"
                />
              </div>
              <div className="space-y-1.5"><Label htmlFor="edit-latest">Latest accepted chapter</Label><Input id="edit-latest" value={latestChapter} onChange={(e) => setLatestChapter(e.target.value)} /></div>
              {item?.pending_latest_chapter && <div className="rounded border border-amber-500/40 p-3 space-y-2 text-sm">
                <p>Check found chapter {item.pending_latest_chapter}. Review before accepting.</p>
                <Input aria-label="Reviewed chapter" value={pendingDecision} onChange={(e) => setPendingDecision(e.target.value)} />
                <Button size="sm" onClick={async () => { try { await itemsApi.resolvePending(item.id, pendingDecision); qc.invalidateQueries({ queryKey: ['items'] }); onOpenChange(false); toast.success('Chapter result resolved.') } catch { toast.error('Could not resolve result.') } }}>Use reviewed chapter</Button>
              </div>}
              <div className="space-y-1.5"><Label htmlFor="edit-note">Personal note</Label><Input id="edit-note" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} /></div>
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={isSensitive} onChange={(e) => setIsSensitive(e.target.checked)} /> Sensitive entry</label>
              <div className="space-y-2 text-sm"><Label>Cover image</Label>
                {coverFilename && item && <img src={`/api/items/${item.id}/cover?${selectedUser ? `user_id=${encodeURIComponent(selectedUser)}&` : ''}v=${encodeURIComponent(coverFilename)}`} alt="Current cover" className="h-24 w-16 object-cover rounded" />}
                <Input type="file" accept="image/png,image/jpeg,image/webp" disabled={coverBusy} onChange={async (e) => { const file = e.target.files?.[0]; if (!file || !item) return; setCoverBusy(true); try { const updated = await itemsApi.uploadCover(item.id, file); setCoverFilename(updated.cover_filename); qc.invalidateQueries({ queryKey: ['items'] }); toast.success('Cover updated.') } catch (error) { toast.error(error instanceof Error ? error.message : 'Cover upload failed.') } finally { setCoverBusy(false); e.target.value = '' } }} />
                <div className="flex gap-2">
                  <Input aria-label="Cover image URL" type="url" placeholder="https://example.com/cover.jpg" value={coverUrl} onChange={(e) => setCoverUrl(e.target.value)} disabled={coverBusy} />
                  <Button size="sm" variant="outline" disabled={!coverUrl.trim() || coverBusy} onClick={async () => { if (!item) return; setCoverBusy(true); try { const updated = await itemsApi.setCoverUrl(item.id, coverUrl.trim()); setCoverFilename(updated.cover_filename); setCoverUrl(''); qc.invalidateQueries({ queryKey: ['items'] }); toast.success('Cover fetched and saved.') } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not fetch cover.') } finally { setCoverBusy(false) } }}>Use URL</Button>
                </div>
                {coverFilename && <Button size="sm" variant="outline" disabled={coverBusy} onClick={async () => { if (!item) return; setCoverBusy(true); try { await itemsApi.removeCover(item.id); setCoverFilename(null); qc.invalidateQueries({ queryKey: ['items'] }); toast.success('Cover removed.') } catch (error) { toast.error(error instanceof Error ? error.message : 'Could not remove cover.') } finally { setCoverBusy(false) } }}>Remove cover</Button>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-category">
                  Category{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Select
                  value={category}
                  onValueChange={(v) => setCategory(v === "__none__" ? "" : v)}
                >
                  <SelectTrigger id="edit-category">
                    <SelectValue placeholder="No category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">No category</SelectItem>
                    {ITEM_CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-interval">Check interval (minutes)</Label>
                <Input
                  id="edit-interval"
                  type="number"
                  min="5"
                  value={interval}
                  onChange={(e) => setInterval(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="edit-active"
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
                <Label htmlFor="edit-active">Active (check for updates)</Label>
              </div>
            </div>
          )}

          {tab === "detection" && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="edit-strategy">Check strategy</Label>
                <Select
                  value={checkStrategy}
                  onValueChange={setCheckStrategy}
                >
                  <SelectTrigger id="edit-strategy">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STRATEGIES.filter((s) => (s.value !== 'COMIX' || item?.original_url.includes('comix.to')) && (s.value !== 'WEBNOVEL' || item?.original_url.includes('webnovel.com')) && (s.value !== 'ROYALROAD' || item?.original_url.includes('royalroad.com')) && (s.value !== 'SCRIBBLEHUB' || item?.original_url.includes('scribblehub.com'))).map((s) => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground leading-snug">
                  {
                    STRATEGIES.find((s) => s.value === checkStrategy)
                      ?.description
                  }
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-toc">
                  Table of contents URL{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Input
                  id="edit-toc"
                  placeholder="https://example.com/series/my-title/"
                  value={tocUrl}
                  onChange={(e) => setTocUrl(e.target.value)}
                />
                <p className="text-[11px] text-muted-foreground leading-snug">
                  Required for <em>ToC scan</em> strategies. The page must list
                  actual series chapter links. A URL template is optional.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-chapter-example">Chapter URL example (optional)</Label>
                <Input
                  id="edit-chapter-example"
                  type="url"
                  placeholder="https://example.com/series/chapter-63"
                  value={chapterExampleUrl}
                  onChange={(e) => {
                    setChapterExampleUrl(e.target.value);
                    patternPreview.reset();
                  }}
                />
                <p className="text-[11px] text-muted-foreground leading-snug">
                  Optional for sequential URL probing. A site checker or ToC scan can work without it. An example cannot make a ToC page with no chapter links scannable.
                </p>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={!chapterExampleUrl.trim() || patternPreview.isPending}
                  onClick={() => patternPreview.mutate({ url: chapterExampleUrl.trim(), manual_regex: manualRegex.trim() || null })}
                >
                  Preview pattern
                </Button>
                {patternPreview.data && (
                  <div className="rounded border border-border bg-muted/30 p-2 text-xs space-y-1">
                    {patternPreview.data.url_template ? (
                      <p className="break-all">Detected URL template: <span className="font-mono">{patternPreview.data.url_template}</span></p>
                    ) : (
                      <p className="text-amber-400">
                        {['opaque_id', 'ambiguous_id'].includes(patternPreview.data.strategy_used)
                          ? 'This URL has another numeric ID. Sequential probing cannot predict the next URL; a ToC scan can use your regex and actual links.'
                          : 'No reusable chapter URL pattern was found. You can save the item for manual tracking.'}
                      </p>
                    )}
                  </div>
                )}
                {patternPreview.isError && <p className="text-xs text-destructive">Could not detect a pattern. Check the URL and regex.</p>}
                {!chapterExampleUrl && item?.url_template && (
                  <div className="text-[11px] text-muted-foreground break-all">
                    <p>Saved URL template: <span className="font-mono">{item.url_template}</span></p>
                    {hasAmbiguousChapterIds(item.url_template) &&
                      <p className="text-amber-500">This URL has separate path and query chapter values, so its template is ignored for probing. Your chapter regex still guides the ToC scan.</p>}
                  </div>
                )}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-regex">
                  Chapter regex override{" "}
                  <span className="text-muted-foreground font-normal">
                    (one capture group)
                  </span>
                </Label>
                <Input
                  id="edit-regex"
                  value={manualRegex}
                  onChange={(e) => { setManualRegex(e.target.value); patternPreview.reset(); }}
                  placeholder="chapter-(\d+)"
                  className="font-mono text-xs"
                />
                <p className="text-[11px] text-muted-foreground leading-snug">
                  Overrides detection when you provide a chapter example. Leave blank to detect from that example automatically.
                </p>
                {item?.pattern_source === 'AUTO' && item.chapter_regex && !manualRegex && (
                  <p className="text-[11px] text-muted-foreground break-all">Saved detected regex: <span className="font-mono">{item.chapter_regex}</span></p>
                )}
              </div>
              <TocExtractionPanel key={`${checkStrategy}:${tocUrl.trim() || item?.series_url || item?.original_url || ''}:${chapterExampleUrl}:${manualRegex}`} tocUrl={tocUrl.trim() || item?.series_url || item?.original_url || ''}
                chapterExampleUrl={chapterExampleUrl}
                fallbackChapterUrl={item?.url_template?.replace('{n}', item?.latest_chapter || item?.current_chapter || '1') || ''}
                strategyOverride={checkStrategy} chapterRegex={manualRegex} onStrategyChange={setCheckStrategy}
                exampleUrls={tocExamples} setExampleUrls={setTocExamples}
                rowHtml={tocRowHtml} setRowHtml={setTocRowHtml}
                savedRowClass={clearRowHint ? null : item?.toc_row_class}
                onClearRowClass={() => { setClearRowHint(true); setTocRowHtml('') }}
                  preferredGroup={preferredGroup} setPreferredGroup={setPreferredGroup} />
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={update.isPending}>
            {update.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
