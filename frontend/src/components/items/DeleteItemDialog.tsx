import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useDeleteItem } from '@/hooks/useItems'
import { toast } from 'sonner'
import type { ItemRead } from '@/types/api'

interface DeleteItemDialogProps {
  item: ItemRead | null
  onOpenChange: (open: boolean) => void
}

export function DeleteItemDialog({ item, onOpenChange }: DeleteItemDialogProps) {
  const deleteItem = useDeleteItem()

  function handleDelete() {
    if (!item) return
    deleteItem.mutate(item.id, {
      onSuccess: () => {
        toast.success('Item deleted.')
        onOpenChange(false)
      },
      onError: () => toast.error('Failed to delete item.'),
    })
  }

  return (
    <Dialog open={item !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete item?</DialogTitle>
          <DialogDescription>
            This will permanently remove{' '}
            <span className="font-medium text-foreground">
              {item?.title ?? item?.original_url ?? 'this item'}
            </span>{' '}
            and all its check history. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            disabled={deleteItem.isPending}
          >
            {deleteItem.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Delete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
