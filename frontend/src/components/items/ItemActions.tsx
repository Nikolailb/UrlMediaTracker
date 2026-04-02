import { ExternalLink, MoreHorizontal, Pencil, RefreshCw, Trash2, BookCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { useCheckItem, useMarkRead } from '@/hooks/useItems'
import { itemsApi } from '@/api/items'
import { toast } from 'sonner'
import type { ItemRead } from '@/types/api'

interface ItemActionsProps {
  item: ItemRead
  onEdit: () => void
  onDelete: () => void
}

export function ItemActions({ item, onEdit, onDelete }: ItemActionsProps) {
  const checkItem = useCheckItem()
  const markRead = useMarkRead()

  async function handleOpenNext() {
    try {
      const res = await itemsApi.next(item.id)
      if (res.next_url) {
        window.open(res.next_url, '_blank', 'noopener,noreferrer')
      } else {
        toast.info(res.message)
      }
    } catch {
      toast.error('Could not fetch next chapter URL.')
    }
  }

  async function handleMarkNextRead() {
    try {
      const res = await itemsApi.next(item.id)
      if (res.next_chapter) {
        markRead.mutate(
          { id: item.id, data: { chapter: res.next_chapter } },
          {
            onSuccess: () => toast.success(`Marked chapter ${res.next_chapter} as read.`),
            onError: () => toast.error('Failed to mark as read.'),
          },
        )
      } else {
        toast.info(res.message)
      }
    } catch {
      toast.error('Could not determine next chapter.')
    }
  }

  function handleCheck() {
    checkItem.mutate(item.id, {
      onSuccess: (data) => {
        if (data.new_latest_chapter) {
          toast.success(`New chapter found: ${data.new_latest_chapter}`)
        } else if (data.success) {
          toast.info('Already up to date.')
        } else {
          toast.warning(data.error_message ?? 'Check completed with warnings.')
        }
      },
      onError: () => toast.error('Failed to check for updates.'),
    })
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Item actions">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel className="text-xs">Actions</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleOpenNext} disabled={!item.url_template}>
          <ExternalLink className="mr-2 h-4 w-4" />
          Open next chapter
        </DropdownMenuItem>
        <DropdownMenuItem onClick={handleMarkNextRead} disabled={!item.has_unread}>
          <BookCheck className="mr-2 h-4 w-4" />
          Mark next as read
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleCheck} disabled={checkItem.isPending}>
          <RefreshCw className={`mr-2 h-4 w-4 ${checkItem.isPending ? 'animate-spin' : ''}`} />
          Check for updates
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={onEdit}>
          <Pencil className="mr-2 h-4 w-4" />
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem
          onClick={onDelete}
          className="text-destructive focus:text-destructive"
        >
          <Trash2 className="mr-2 h-4 w-4" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
