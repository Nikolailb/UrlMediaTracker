import { Badge } from '@/components/ui/badge'
import { ItemProgress } from './ItemProgress'
import { ItemActions } from './ItemActions'
import { RelativeTime } from '@/components/ui/relative-time'
import type { ItemRead } from '@/types/api'
import { ReadingActions } from './ReadingActions'
import { useAuth } from '@/auth/context'

interface ItemCardsProps {
  items: ItemRead[]
  onEdit: (item: ItemRead) => void
  onDelete: (item: ItemRead) => void
  onHistory: (item: ItemRead) => void
}

export function ItemCards({ items, onEdit, onDelete, onHistory }: ItemCardsProps) {
  const { selectedUser } = useAuth()
  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.id}
          className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3 transition-shadow hover:shadow-md"
        >
          <div className="flex gap-3">
            {item.cover_filename ? <img src={`/api/items/${item.id}/cover${selectedUser ? `?user_id=${encodeURIComponent(selectedUser)}` : ''}`} alt={`${item.title ?? 'Series'} cover`} className="h-24 w-16 shrink-0 rounded object-cover" /> : <div aria-hidden="true" className="h-24 w-16 shrink-0 rounded bg-muted flex items-center justify-center text-xs text-muted-foreground">No cover</div>}
          {/* Header row */}
          <div className="flex min-w-0 flex-1 items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <a href={item.toc_url ?? item.series_url ?? item.original_url} target="_blank" rel="noopener noreferrer" className="font-medium truncate text-sm hover:text-primary hover:underline underline-offset-2" title="Open series or table of contents">
                  {item.title ?? new URL(item.original_url).hostname}
                </a>
                {item.has_unread && (
                  <span className="h-2 w-2 shrink-0 rounded-full bg-primary animate-pulse" />
                )}
              </div>
            </div>
            <ItemActions item={item} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} onHistory={() => onHistory(item)} />
          </div>
          </div>

          {/* Progress */}
          <ItemProgress item={item} />
          {item.note && <p className="text-xs text-muted-foreground line-clamp-2">{item.note}</p>}
          {item.pending_latest_chapter && <p className="text-xs text-amber-600">Chapter {item.pending_latest_chapter} needs review</p>}
          {item.last_outcome === 'FAILED' || item.last_outcome === 'BLOCKED' ? <p className="text-xs text-amber-600">Check issue: {item.last_error ?? item.last_outcome}</p> : null}
          <ReadingActions item={item} />

          {/* Footer */}
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground pt-1 border-t border-border">
            <span>Checked <RelativeTime iso={item.last_checked_at} /></span>
            <div className="flex flex-wrap items-center gap-1.5">
              {item.category && (
                <Badge variant="outline" className="text-[10px]">{item.category}</Badge>
              )}
              {item.is_sensitive && <Badge variant="secondary" className="text-[10px]">Sensitive</Badge>}
              <Badge variant={item.is_active ? 'success' : 'secondary'} className="text-[10px]">
                {item.is_active ? 'Active' : 'Paused'}
              </Badge>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
