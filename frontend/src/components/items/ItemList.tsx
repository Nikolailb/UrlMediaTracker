import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, Plus, Search, SlidersHorizontal, Trash2, Upload, PauseCircle, PlayCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
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
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { ItemTable } from './ItemTable'
import { ItemCards } from './ItemCards'
import { AddItemDialog } from './AddItemDialog'
import { EditItemDialog } from './EditItemDialog'
import { DeleteItemDialog } from './DeleteItemDialog'
import { CheckHistoryDialog } from './CheckHistoryDialog'
import { useItems, useBulkDelete, useBulkPause, useBulkResume, useImportItems } from '@/hooks/useItems'
import { itemsApi } from '@/api/items'
import { chapterToFloat } from '@/lib/utils'
import { toast } from 'sonner'
import type { ItemRead } from '@/types/api'
import { ITEM_CATEGORIES } from '@/types/api'

type SortKey = 'title' | 'created_at' | 'last_checked_at' | 'has_unread'
type SortDir = 'asc' | 'desc'

function useWindowWidth() {
  const [width, setWidth] = useState(() => window.innerWidth)
  useEffect(() => {
    const handler = () => setWidth(window.innerWidth)
    window.addEventListener('resize', handler)
    return () => window.removeEventListener('resize', handler)
  }, [])
  return width
}

export function ItemList() {
  const [addOpen, setAddOpen] = useState(false)
  const [editItem, setEditItem] = useState<ItemRead | null>(null)
  const [deleteItem, setDeleteItem] = useState<ItemRead | null>(null)
  const [historyItem, setHistoryItem] = useState<ItemRead | null>(null)

  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(true)
  const [showUnreadOnly, setShowUnreadOnly] = useState(false)
  const [categoryFilter, setCategoryFilter] = useState<string>('')
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  // Bulk selection
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const importRef = useRef<HTMLInputElement>(null)

  const { data: items, isLoading, error } = useItems()
  const width = useWindowWidth()
  const isMobile = width < 768

  const bulkDelete = useBulkDelete()
  const bulkPause = useBulkPause()
  const bulkResume = useBulkResume()
  const importItems = useImportItems()

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const filtered = useMemo(() => {
    if (!items) return []
    let result = [...items]

    if (!showInactive) result = result.filter((i) => i.is_active)
    if (showUnreadOnly) result = result.filter((i) => i.has_unread === true)
    if (categoryFilter) result = result.filter((i) => i.category === categoryFilter)

    if (search.trim()) {
      const q = search.toLowerCase()
      result = result.filter(
        (i) =>
          i.original_url.toLowerCase().includes(q) ||
          i.title?.toLowerCase().includes(q),
      )
    }

    result.sort((a, b) => {
      let cmp = 0
      switch (sortKey) {
        case 'title':
          cmp = (a.title ?? a.original_url).localeCompare(b.title ?? b.original_url)
          break
        case 'created_at':
          cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          break
        case 'last_checked_at':
          cmp =
            new Date(a.last_checked_at ?? 0).getTime() -
            new Date(b.last_checked_at ?? 0).getTime()
          break
        case 'has_unread':
          cmp =
            chapterToFloat(a.latest_chapter) -
            chapterToFloat(a.current_chapter) -
            (chapterToFloat(b.latest_chapter) - chapterToFloat(b.current_chapter))
          break
      }
      return sortDir === 'asc' ? cmp : -cmp
    })

    return result
  }, [items, search, showInactive, showUnreadOnly, categoryFilter, sortKey, sortDir])

  // Clear invalid selections when filtered list changes
  useEffect(() => {
    const validIds = new Set(filtered.map((i) => i.id))
    setSelected((prev) => {
      const next = new Set([...prev].filter((id) => validIds.has(id)))
      return next.size === prev.size ? prev : next
    })
  }, [filtered])

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAll() {
    if (selected.size === filtered.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(filtered.map((i) => i.id)))
    }
  }

  async function handleExport() {
    try {
      const data = await itemsApi.exportAll()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `tracker-export-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
      toast.success(`Exported ${data.length} item${data.length !== 1 ? 's' : ''}.`)
    } catch {
      toast.error('Export failed.')
    }
  }

  function handleImportClick() {
    importRef.current?.click()
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ''
    try {
      const text = await file.text()
      const records = JSON.parse(text)
      if (!Array.isArray(records)) { toast.error('Import file must be a JSON array.'); return }
      importItems.mutate(records, {
        onSuccess: (res) => toast.success(`Imported ${res.created} item(s), skipped ${res.skipped} duplicate(s).`),
        onError: () => toast.error('Import failed.'),
      })
    } catch {
      toast.error('Could not parse import file.')
    }
  }

  function handleBulkDelete() {
    const ids = [...selected]
    bulkDelete.mutate(ids, {
      onSuccess: (res) => { toast.success(`Deleted ${res.deleted} item(s).`); setSelected(new Set()) },
      onError: () => toast.error('Bulk delete failed.'),
    })
  }

  function handleBulkPause() {
    bulkPause.mutate([...selected], {
      onSuccess: (res) => { toast.success(`Paused ${res.paused} item(s).`); setSelected(new Set()) },
      onError: () => toast.error('Bulk pause failed.'),
    })
  }

  function handleBulkResume() {
    bulkResume.mutate([...selected], {
      onSuccess: (res) => { toast.success(`Resumed ${res.resumed} item(s).`); setSelected(new Set()) },
      onError: () => toast.error('Bulk resume failed.'),
    })
  }

  const activeFilterCount =
    (showUnreadOnly ? 1 : 0) + (!showInactive ? 1 : 0) + (categoryFilter ? 1 : 0)

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

      {/* Toolbar */}
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

        <div className="flex items-center gap-2">
          {/* Filter / sort menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-2">
                <SlidersHorizontal className="h-4 w-4" />
                Filters
                {activeFilterCount > 0 && (
                  <Badge variant="default" className="h-4 w-4 rounded-full p-0 flex items-center justify-center text-[10px]">
                    {activeFilterCount}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 p-0">
              <div className="px-1 py-1 border-b border-border flex items-center justify-between">
                <span className="px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">Filters &amp; sort</span>
                {activeFilterCount > 0 && (
                  <DropdownMenuItem
                    className="h-6 px-2 text-xs text-destructive focus:text-destructive cursor-pointer"
                    onSelect={() => {
                      setShowInactive(true)
                      setShowUnreadOnly(false)
                      setCategoryFilter('')
                    }}
                  >
                    Clear filters
                  </DropdownMenuItem>
                )}
              </div>
              <div className="overflow-y-auto max-h-[min(24rem,calc(100dvh-8rem))] py-1">
              <DropdownMenuCheckboxItem checked={showInactive} onCheckedChange={setShowInactive}>
                Show inactive items
              </DropdownMenuCheckboxItem>
              <DropdownMenuCheckboxItem checked={showUnreadOnly} onCheckedChange={setShowUnreadOnly}>
                Unread only
              </DropdownMenuCheckboxItem>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Category</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuRadioGroup value={categoryFilter} onValueChange={setCategoryFilter}>
                <DropdownMenuRadioItem value="">All categories</DropdownMenuRadioItem>
                {ITEM_CATEGORIES.map((c) => (
                  <DropdownMenuRadioItem key={c} value={c}>{c}</DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuLabel>Sort by</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuRadioGroup value={sortKey} onValueChange={(v) => setSortKey(v as SortKey)}>
                <DropdownMenuRadioItem value="created_at">Date added</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="title">Title</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="last_checked_at">Last checked</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="has_unread">Unread gap</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              <DropdownMenuSeparator />
              <DropdownMenuRadioGroup value={sortDir} onValueChange={(v) => setSortDir(v as SortDir)}>
                <DropdownMenuRadioItem value="desc">Descending</DropdownMenuRadioItem>
                <DropdownMenuRadioItem value="asc">Ascending</DropdownMenuRadioItem>
              </DropdownMenuRadioGroup>
              </div>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Import / export */}
          <Button variant="outline" size="sm" onClick={handleImportClick} title="Import from JSON">
            <Upload className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport} title="Export to JSON">
            <Download className="h-4 w-4" />
          </Button>

          <Button onClick={() => setAddOpen(true)} size="sm" className="gap-2">
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>
      </div>

      {/* Bulk action bar */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-2 text-sm">
          <span className="font-medium">{selected.size} selected</span>
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
          {filtered.length} of {items.length} item{items.length !== 1 ? 's' : ''}
          {activeFilterCount > 0 ? ' (filtered)' : ''}
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
            {items?.length === 0 ? 'No tracked items yet.' : 'No items match your filters.'}
          </p>
          {items?.length === 0 && (
            <Button onClick={() => setAddOpen(true)}>Add your first item</Button>
          )}
        </div>
      )}

      {/* List */}
      {!isLoading && !error && filtered.length > 0 && (
        isMobile ? (
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
            selected={selected}
            onSelect={toggleSelect}
            onSelectAll={toggleSelectAll}
          />
        )
      )}

      {/* Dialogs */}
      <AddItemDialog open={addOpen} onOpenChange={setAddOpen} />
      <EditItemDialog item={editItem} onOpenChange={(o) => { if (!o) setEditItem(null) }} />
      <DeleteItemDialog item={deleteItem} onOpenChange={(o) => { if (!o) setDeleteItem(null) }} />
      <CheckHistoryDialog item={historyItem} onOpenChange={(o) => { if (!o) setHistoryItem(null) }} />
    </div>
  )
}
