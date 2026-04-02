import { useEffect, useMemo, useState } from 'react'
import { Plus, Search, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
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
import { useItems } from '@/hooks/useItems'
import { chapterToFloat } from '@/lib/utils'
import type { ItemRead } from '@/types/api'

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

  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(true)
  const [showUnreadOnly, setShowUnreadOnly] = useState(false)
  const [sortKey, setSortKey] = useState<SortKey>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  const { data: items, isLoading, error } = useItems()
  const width = useWindowWidth()
  const isMobile = width < 768

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
  }, [items, search, showInactive, showUnreadOnly, sortKey, sortDir])

  return (
    <div className="space-y-4">
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
                {(showUnreadOnly || !showInactive) && (
                  <Badge variant="default" className="h-4 w-4 rounded-full p-0 flex items-center justify-center text-[10px]">
                    {(showUnreadOnly ? 1 : 0) + (!showInactive ? 1 : 0)}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuLabel>Filters</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuCheckboxItem checked={showInactive} onCheckedChange={setShowInactive}>
                Show inactive items
              </DropdownMenuCheckboxItem>
              <DropdownMenuCheckboxItem checked={showUnreadOnly} onCheckedChange={setShowUnreadOnly}>
                Unread only
              </DropdownMenuCheckboxItem>
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
            </DropdownMenuContent>
          </DropdownMenu>

          <Button onClick={() => setAddOpen(true)} size="sm" className="gap-2">
            <Plus className="h-4 w-4" />
            Add
          </Button>
        </div>
      </div>

      {/* Count */}
      {items && (
        <p className="text-xs text-muted-foreground">
          {filtered.length} of {items.length} item{items.length !== 1 ? 's' : ''}
          {showUnreadOnly || !showInactive ? ' (filtered)' : ''}
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
          <ItemCards items={filtered} onEdit={setEditItem} onDelete={setDeleteItem} />
        ) : (
          <ItemTable
            items={filtered}
            sortKey={sortKey}
            sortDir={sortDir}
            onSort={handleSort}
            onEdit={setEditItem}
            onDelete={setDeleteItem}
          />
        )
      )}

      {/* Dialogs */}
      <AddItemDialog open={addOpen} onOpenChange={setAddOpen} />
      <EditItemDialog item={editItem} onOpenChange={(o) => { if (!o) setEditItem(null) }} />
      <DeleteItemDialog item={deleteItem} onOpenChange={(o) => { if (!o) setDeleteItem(null) }} />
    </div>
  )
}
