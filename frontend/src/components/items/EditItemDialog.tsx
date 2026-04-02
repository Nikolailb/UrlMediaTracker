import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogDescription,
  DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { useUpdateItem } from '@/hooks/useItems'
import { toast } from 'sonner'
import type { ItemRead } from '@/types/api'

interface EditItemDialogProps {
  item: ItemRead | null
  onOpenChange: (open: boolean) => void
}

export function EditItemDialog({ item, onOpenChange }: EditItemDialogProps) {
  const open = item !== null
  const [title, setTitle] = useState('')
  const [manualRegex, setManualRegex] = useState('')
  const [interval, setInterval] = useState('60')
  const [currentChapter, setCurrentChapter] = useState('')
  const [isActive, setIsActive] = useState(true)

  const update = useUpdateItem()

  useEffect(() => {
    if (item) {
      setTitle(item.title ?? '')
      setManualRegex(item.chapter_regex ?? '')
      setInterval(String(item.check_interval_min))
      setCurrentChapter(item.current_chapter ?? '')
      setIsActive(item.is_active)
    }
  }, [item])

  function handleSubmit() {
    if (!item) return
    update.mutate(
      {
        id: item.id,
        data: {
          title: title.trim() || null,
          manual_regex: manualRegex.trim() || null,
          check_interval_min: parseInt(interval) || 60,
          current_chapter: currentChapter.trim() || null,
          is_active: isActive,
        },
      },
      {
        onSuccess: () => {
          toast.success('Item updated.')
          onOpenChange(false)
        },
        onError: (err) => toast.error(err.message),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit item</DialogTitle>
          <DialogDescription>Update details for this tracked item.</DialogDescription>
        </DialogHeader>

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

          <div className="space-y-1.5">
            <Label htmlFor="edit-regex">
              Chapter regex override{' '}
              <span className="text-muted-foreground font-normal">(one capture group)</span>
            </Label>
            <Input
              id="edit-regex"
              value={manualRegex}
              onChange={(e) => setManualRegex(e.target.value)}
              placeholder="chapter-(\d+)"
              className="font-mono text-xs"
            />
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

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={update.isPending}>
            {update.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
