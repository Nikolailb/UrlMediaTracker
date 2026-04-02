import { ExternalLink } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { ItemProgress } from './ItemProgress'
import { ItemActions } from './ItemActions'
import { RelativeTime } from '@/components/ui/relative-time'
import type { ItemRead } from '@/types/api'

interface ItemCardsProps {
  items: ItemRead[]
  onEdit: (item: ItemRead) => void
  onDelete: (item: ItemRead) => void
}

export function ItemCards({ items, onEdit, onDelete }: ItemCardsProps) {
  return (
    <div className="grid gap-3 grid-cols-1 sm:grid-cols-2">
      {items.map((item) => (
        <div
          key={item.id}
          className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3 transition-shadow hover:shadow-md"
        >
          {/* Header row */}
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="font-medium truncate text-sm">
                  {item.title ?? new URL(item.original_url).hostname}
                </span>
                {item.has_unread && (
                  <span className="h-2 w-2 shrink-0 rounded-full bg-primary animate-pulse" />
                )}
              </div>
              <a
                href={item.original_url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 mt-0.5 text-xs text-muted-foreground hover:text-primary truncate"
              >
                <ExternalLink className="h-3 w-3 shrink-0" />
                <span className="truncate">{item.original_url}</span>
              </a>
            </div>
            <ItemActions item={item} onEdit={() => onEdit(item)} onDelete={() => onDelete(item)} />
          </div>

          {/* Progress */}
          <ItemProgress item={item} />

          {/* Footer */}
          <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border">
            <span>Checked <RelativeTime iso={item.last_checked_at} /></span>
            <Badge variant={item.is_active ? 'success' : 'secondary'} className="text-[10px]">
              {item.is_active ? 'Active' : 'Paused'}
            </Badge>
          </div>
        </div>
      ))}
    </div>
  )
}
