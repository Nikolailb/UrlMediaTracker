import { useEffect, useMemo, useRef, useState } from "react";
import {
  Download,
  Plus,
  Search,
  SlidersHorizontal,
  Trash2,
  Upload,
  PauseCircle,
  PlayCircle,
  LayoutGrid,
  List,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { ItemTable } from "./ItemTable";
import { ItemCards } from "./ItemCards";
import { AddItemDialog } from "./AddItemDialog";
import { EditItemDialog } from "./EditItemDialog";
import { DeleteItemDialog } from "./DeleteItemDialog";
import { CheckHistoryDialog } from "./CheckHistoryDialog";
import {
  useItems,
  useBulkDelete,
  useBulkPause,
  useBulkResume,
  useImportItems,
} from "@/hooks/useItems";
import { itemsApi } from "@/api/items";
import { chapterToFloat } from "@/lib/utils";
import { toast } from "sonner";
import type { ItemRead } from "@/types/api";
import { ITEM_CATEGORIES } from "@/types/api";
import type { FilterPreset, ItemCategory } from "@/types/api";
import { useFilterPresets } from '@/hooks/useFilterPresets'
import { useAuth } from '@/auth/context'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { FilterPresetDialog } from './FilterPresetDialog'
import { SiteTestDialog } from './SiteTestDialog'
import { ArchiveDialog } from './ArchiveDialog'

type SortKey =
  | "title"
  | "created_at"
  | "latest_chapter_at"
  | "last_checked_at"
  | "has_unread";
type SortDir = "asc" | "desc";

function useWindowWidth() {
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);
  return width;
}

export function ItemList() {
  const { selectedUser } = useAuth();
  return <ItemListContent key={selectedUser} />;
}

function ItemListContent() {
  const [addOpen, setAddOpen] = useState(false);
  const [editItem, setEditItem] = useState<ItemRead | null>(null);
  const [deleteItem, setDeleteItem] = useState<ItemRead | null>(null);
  const [historyItem, setHistoryItem] = useState<ItemRead | null>(null);
  const [siteTestOpen, setSiteTestOpen] = useState(false)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [presetDialogOpen, setPresetDialogOpen] = useState(false)
  const [editingPreset, setEditingPreset] = useState<FilterPreset | null>(null)
  const [activePresetId, setActivePresetId] = useState('all')
  const [view, setView] = useState<'table' | 'cards'>(() => (localStorage.getItem('tracker-view') === 'cards' ? 'cards' : 'table'))

  const [search, setSearch] = useState("");
  const [showInactive, setShowInactive] = useState(true);
  const [showUnreadOnly, setShowUnreadOnly] = useState(false);
  const [categories, setCategories] = useState<ItemCategory[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("latest_chapter_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const importRef = useRef<HTMLInputElement>(null);

  const { data: items, isLoading, error } = useItems();
  const { data: presets = [] } = useFilterPresets();
  const width = useWindowWidth();
  const isMobile = width < 768;
  const activeView = isMobile ? 'cards' : view

  const bulkDelete = useBulkDelete();
  const bulkPause = useBulkPause();
  const bulkResume = useBulkResume();
  const importItems = useImportItems();

  const activePreset = presets.find((preset) => preset.id === activePresetId)
  const initialPreset = useMemo(() => ({ categories, unread_only: showUnreadOnly, include_inactive: showInactive }), [categories, showUnreadOnly, showInactive])

  function applyPreset(preset: FilterPreset | null) {
    setCategories(preset?.categories ?? [])
    setShowUnreadOnly(preset?.unread_only ?? false)
    setShowInactive(preset?.include_inactive ?? true)
    setActivePresetId(preset?.id ?? 'all')
  }

  function toggleCategory(category: ItemCategory) {
    setCategories((previous) => previous.includes(category)
      ? previous.filter((value) => value !== category)
      : [...previous, category])
    setActivePresetId('custom')
  }

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  }

  const filtered = useMemo(() => {
    if (!items) return [];
    let result = [...items];

    if (!showInactive) result = result.filter((i) => i.is_active);
    if (showUnreadOnly) result = result.filter((i) => i.has_unread === true);
    if (categories.length)
      result = result.filter((i) => categories.includes(i.category as ItemCategory));

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (i) =>
          i.original_url.toLowerCase().includes(q) ||
          i.title?.toLowerCase().includes(q),
      );
    }

    result.sort((a, b) => {
      let cmp = 0;
      switch (sortKey) {
        case "title":
          cmp = (a.title ?? a.original_url).localeCompare(
            b.title ?? b.original_url,
          );
          break;
        case "created_at":
          cmp =
            new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
          break;
        case "latest_chapter_at":
          cmp =
            new Date(a.latest_chapter_at ?? 0).getTime() -
            new Date(b.latest_chapter_at ?? 0).getTime();
          break;
        case "last_checked_at":
          cmp =
            new Date(a.last_checked_at ?? 0).getTime() -
            new Date(b.last_checked_at ?? 0).getTime();
          break;
        case "has_unread":
          cmp =
            chapterToFloat(a.latest_chapter) -
            chapterToFloat(a.current_chapter) -
            (chapterToFloat(b.latest_chapter) -
              chapterToFloat(b.current_chapter));
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [
    items,
    search,
    showInactive,
    showUnreadOnly,
    categories,
    sortKey,
    sortDir,
  ]);

  const filteredIds = useMemo(
    () => new Set(filtered.map((i) => i.id)),
    [filtered],
  );

  const visibleSelected = useMemo(
    () => new Set([...selected].filter((id) => filteredIds.has(id))),
    [selected, filteredIds],
  );

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (visibleSelected.size === filtered.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(filtered.map((i) => i.id)));
    }
  }

  async function handleExport() {
    try {
      const data = await itemsApi.exportAll();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `tracker-export-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(
        `Exported ${data.length} item${data.length !== 1 ? "s" : ""}.`,
      );
    } catch {
      toast.error("Export failed.");
    }
  }

  function handleImportClick() {
    importRef.current?.click();
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      const text = await file.text();
      const records = JSON.parse(text);
      if (!Array.isArray(records)) {
        toast.error("Import file must be a JSON array.");
        return;
      }
      importItems.mutate(records, {
        onSuccess: (res) =>
          toast.success(
            `Imported ${res.created} item(s), skipped ${res.skipped} duplicate(s).`,
          ),
        onError: () => toast.error("Import failed."),
      });
    } catch {
      toast.error("Could not parse import file.");
    }
  }

  function handleBulkDelete() {
    const ids = [...visibleSelected];
    bulkDelete.mutate(ids, {
      onSuccess: (res) => {
        toast.success(`Deleted ${res.deleted} item(s).`);
        setSelected(new Set());
      },
      onError: () => toast.error("Bulk delete failed."),
    });
  }

  function handleBulkPause() {
    bulkPause.mutate([...visibleSelected], {
      onSuccess: (res) => {
        toast.success(`Paused ${res.paused} item(s).`);
        setSelected(new Set());
      },
      onError: () => toast.error("Bulk pause failed."),
    });
  }

  function handleBulkResume() {
    bulkResume.mutate([...visibleSelected], {
      onSuccess: (res) => {
        toast.success(`Resumed ${res.resumed} item(s).`);
        setSelected(new Set());
      },
      onError: () => toast.error("Bulk resume failed."),
    });
  }

  const activeFilterCount =
    (showUnreadOnly ? 1 : 0) +
    (!showInactive ? 1 : 0) +
    (categories.length ? 1 : 0);

  return (
    <div className="space-y-4">
      {/* Hidden file input for import */}
      <input
        ref={importRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={handleImportFile}
      />

      {/* Compact preset picker, including on phones. */}
      <div className="flex items-center gap-2 min-w-0" aria-label="Saved filters">
        <label htmlFor="preset-picker" className="sr-only">Filter preset</label>
        <Select value={activePresetId} onValueChange={(id) => {
          if (id === 'all') applyPreset(null)
          else if (id !== 'custom') applyPreset(presets.find((preset) => preset.id === id) ?? null)
        }}>
          <SelectTrigger id="preset-picker" className="h-9 flex-1 min-w-0 max-w-xs" aria-label="Filter preset">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-w-[calc(100vw-2rem)]">
            <SelectItem value="all">All items</SelectItem>
            {activePresetId === 'custom' && <SelectItem value="custom">Custom filter</SelectItem>}
            {presets.map((preset) => <SelectItem key={preset.id} value={preset.id}>{preset.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Button size="sm" variant="outline" className="shrink-0" onClick={() => { setEditingPreset(null); setPresetDialogOpen(true) }}>Save</Button>
        {activePreset && !activePreset.builtin && (
          <Button size="sm" variant="outline" className="shrink-0" onClick={() => { setEditingPreset(activePreset); setPresetDialogOpen(true) }}>Edit</Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground">{filtered.filter((item) => item.has_unread).length} unread · {filtered.filter((item) => item.pending_latest_chapter).length} pending review · {filtered.filter((item) => item.consecutive_failures > 0).length} check issues</p>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
          <Input
            placeholder="Search titles or URLs…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setSiteTestOpen(true)}>Test site</Button>
          <Button variant="outline" size="sm" onClick={() => setArchiveOpen(true)}>Archive</Button>
          {!isMobile && <Button variant="outline" size="sm" title={view === 'table' ? 'Card view' : 'Table view'} onClick={() => { const next = view === 'table' ? 'cards' : 'table'; setView(next); localStorage.setItem('tracker-view', next) }}>{view === 'table' ? <LayoutGrid className="h-4 w-4" /> : <List className="h-4 w-4" />}</Button>}
          {/* Filter / sort menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <SlidersHorizontal className="h-4 w-4" />
                Filters
                {activeFilterCount > 0 && (
                  <Badge
                    variant="default"
                    className="h-4 w-4 rounded-full p-0 flex items-center justify-center text-[10px]"
                  >
                    {activeFilterCount}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 p-0">
              <div className="px-1 py-1 border-b border-border flex items-center justify-between">
                <span className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                  Filters &amp; sort
                </span>
                {activeFilterCount > 0 && (
                  <DropdownMenuItem
                    className="h-6 px-2 text-xs text-destructive focus:text-destructive cursor-pointer"
                    onSelect={() => {
                      setShowInactive(true);
                      setShowUnreadOnly(false);
                      setCategories([]);
                      setActivePresetId('all');
                    }}
                  >
                    Clear filters
                  </DropdownMenuItem>
                )}
              </div>
              <div className="overflow-y-auto max-h-[min(24rem,calc(100dvh-8rem))] py-1">
                <DropdownMenuCheckboxItem
                  checked={showInactive}
                  onCheckedChange={(value) => { setShowInactive(value); setActivePresetId('custom') }}
                >
                  Show inactive items
                </DropdownMenuCheckboxItem>
                <DropdownMenuCheckboxItem
                  checked={showUnreadOnly}
                  onCheckedChange={(value) => { setShowUnreadOnly(value); setActivePresetId('custom') }}
                >
                  Unread only
                </DropdownMenuCheckboxItem>
                <DropdownMenuSeparator />
                <DropdownMenuLabel>Categories (any selected)</DropdownMenuLabel>
                <DropdownMenuSeparator />
                  {ITEM_CATEGORIES.map((c) => (
                    <DropdownMenuCheckboxItem key={c} checked={categories.includes(c)} onCheckedChange={() => toggleCategory(c)} onSelect={(event) => event.preventDefault()}>
                      {c}
                    </DropdownMenuCheckboxItem>
                  ))}
                <DropdownMenuSeparator />
                <DropdownMenuLabel>Sort by</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup
                  value={sortKey}
                  onValueChange={(v) => setSortKey(v as SortKey)}
                >
                  <DropdownMenuRadioItem value="latest_chapter_at">
                    Recently updated
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="created_at">
                    Date added
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="title">
                    Title
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="last_checked_at">
                    Last checked
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="has_unread">
                    Unread gap
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup
                  value={sortDir}
                  onValueChange={(v) => setSortDir(v as SortDir)}
                >
                  <DropdownMenuRadioItem value="desc">
                    Descending
                  </DropdownMenuRadioItem>
                  <DropdownMenuRadioItem value="asc">
                    Ascending
                  </DropdownMenuRadioItem>
                </DropdownMenuRadioGroup>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Import / export */}
          <Button
            variant="outline"
            size="sm"
            onClick={handleImportClick}
            title="Import from JSON"
          >
            <Upload className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleExport}
            title="Export to JSON"
          >
            <Download className="h-4 w-4" />
          </Button>

          <Button onClick={() => setAddOpen(true)} size="sm" className="gap-2">
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>
      </div>

      {/* Bulk action bar */}
      {visibleSelected.size > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-2 text-sm">
          <span className="font-medium">{visibleSelected.size} selected</span>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={handleBulkPause}
            disabled={bulkPause.isPending}
          >
            <PauseCircle className="h-4 w-4" /> Pause
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={handleBulkResume}
            disabled={bulkResume.isPending}
          >
            <PlayCircle className="h-4 w-4" /> Resume
          </Button>
          <Button
            variant="destructive"
            size="sm"
            className="gap-1.5"
            onClick={handleBulkDelete}
            disabled={bulkDelete.isPending}
          >
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => setSelected(new Set())}
          >
            Clear
          </Button>
        </div>
      )}

      {/* Count */}
      {items && (
        <p className="text-xs text-muted-foreground">
          {filtered.length} of {items.length} item
          {items.length !== 1 ? "s" : ""}
          {activeFilterCount > 0 ? " (filtered)" : ""}
        </p>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="space-y-2">
          {[...Array(4)].map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          Failed to load items. Is the backend running?
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !error && filtered.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
          <p className="text-muted-foreground text-sm">
            {items?.length === 0
              ? "No tracked items yet."
              : "No items match your filters."}
          </p>
          {items?.length === 0 && (
            <Button onClick={() => setAddOpen(true)}>
              Add your first item
            </Button>
          )}
        </div>
      )}

      {/* List */}
      {!isLoading &&
        !error &&
        filtered.length > 0 &&
        (activeView === 'cards' ? (
          <ItemCards
            items={filtered}
            onEdit={setEditItem}
            onDelete={setDeleteItem}
            onHistory={setHistoryItem}
          />
        ) : (
          <ItemTable
            items={filtered}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
            onEdit={setEditItem}
            onDelete={setDeleteItem}
            onHistory={setHistoryItem}
            selected={visibleSelected}
            onSelect={toggleSelect}
            onSelectAll={toggleSelectAll}
          />
        ))}

      {/* Dialogs */}
      <AddItemDialog open={addOpen} onOpenChange={setAddOpen} />
      <SiteTestDialog open={siteTestOpen} onOpenChange={setSiteTestOpen} />
      <ArchiveDialog open={archiveOpen} onOpenChange={setArchiveOpen} />
      <FilterPresetDialog
        open={presetDialogOpen}
        onOpenChange={setPresetDialogOpen}
        preset={editingPreset}
        initial={initialPreset}
        onSaved={applyPreset}
        onDeleted={() => applyPreset(null)}
      />
      <EditItemDialog
        key={editItem?.id ?? "edit-empty"}
        item={editItem}
        onOpenChange={(o) => {
          if (!o) setEditItem(null);
        }}
      />
      <DeleteItemDialog
        item={deleteItem}
        onOpenChange={(o) => {
          if (!o) setDeleteItem(null);
        }}
      />
      <CheckHistoryDialog
        item={historyItem}
        onOpenChange={(o) => {
          if (!o) setHistoryItem(null);
        }}
      />
    </div>
  );
}
