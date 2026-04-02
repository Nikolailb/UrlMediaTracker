import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ItemProgress } from './ItemProgress'
import { ItemActions } from './ItemActions'
import { formatRelativeDate } from '@/lib/utils'
import type { ItemRead } from '@/types/api'

type SortKey = 'title' | 'created_at' | 'last_checked_at' | 'has_unread'
type SortDir = 'asc' | 'desc'

interface ItemTableProps {
  items: ItemRead[]
  sortKey: SortKey
  sortDir: SortDir
  onSort: (key: SortKey) => void
  onEdit: (item: ItemRead) => void
  onDelete: (item: ItemRead) => void
}

export function ItemTable({ items, sortKey, sortDir, onSort, onEdit, onDelete }: ItemTableProps) {
  function SortButton({ col, label }: { col: SortKey; label: string }) {
    const active = sortKey === col
    const Icon = active ? (sortDir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown
    return (
      <Button
        variant="ghost"
        size="sm"
        className={`-ml-2 gap-1 text-xs font-semibold uppercase tracking-wide ${active ? 'text-foreground' : 'text-muted-foreground'}`}
        onClick={() => onSort(col)}
      >
        {label}
        <Icon className={`h-3 w-3 ${active ? 'opacity-100' : 'opacity-40'}`} />
      </Button>
    )
  }

  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted/40">
          <tr className="border-b border-border">
            <th className="px-4 py-3 text-left">
              <SortButton col="title" label="Title / URL" />
            </th>
            <th className="px-4 py-3 text-left hidden md:table-cell">
              <SortButton col="has_unread" label="Progress" />
            </th>
            <th className="px-4 py-3 text-left hidden lg:table-cell">
              <SortButton col="last_checked_at" label="Last checked" />
            </th>
            <th className="px-4 py-3 text-left hidden sm:table-cell">Status</th>
            <th className="px-4 py-3 w-12" />
          </tr>
        </thead>
        <tbody>
          {items.map((item, i) => (
            <tr
              key={item.id}
              className={`border-b border-border last:border-0 transition-colors hover:bg-muted/20 ${i % 2 === 0 ? '' : 'bg-muted/5'}`}
            >
              {/* Title / URL */}
              <td className="px-4 py-3">
                <div className="flex flex-col gap-0.5 min-w-0">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className="font-medium truncate max-w-[200px] sm:max-w-xs">
                      {item.title ?? new URL(item.original_url).hostname}
                    </span>
                    {item.has_unread && (
                      <span className="shrink-0 h-2 w-2 rounded-full bg-primary animate-pulse" />
                    )}
                  </div>
                  <a
                    href={item.original_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-primary truncate max-w-[200px] sm:max-w-xs"
                  >
                    <ExternalLink className="h-3 w-3 shrink-0" />
                    <span className="truncate">{item.original_url}</span>
                  </a>
                  {/* Progress inline on small screens */}
                  <div className="md:hidden mt-1">
                    <ItemProgress item={item} />
                  </div>
                </div>
              </td>

              {/* Progress */}
              <td className="px-4 py-3 hidden md:table-cell">
                <ItemProgress item={item} />
              </td>

              {/* Last checked */}
              <td className="px-4 py-3 hidden lg:table-cell text-muted-foreground text-xs">
                {formatRelativeDate(item.last_checked_at)}
              </td>

              {/* Status */}
              <td className="px-4 py-3 hidden sm:table-cell">
                <Badge variant={item.is_active ? 'success' : 'secondary'}>
                  {item.is_active ? 'Active' : 'Paused'}
                </Badge>
              </td>

              {/* Actions */}
              <td className="px-2 py-3">
                <ItemActions item={item} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
