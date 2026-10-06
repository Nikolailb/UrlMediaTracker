import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import type { FilterPreset, FilterPresetInput } from '@/types/api'
import { useCreateFilterPreset, useDeleteFilterPreset, useUpdateFilterPreset } from '@/hooks/useFilterPresets'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  preset: FilterPreset | null
  initial: Omit<FilterPresetInput, 'name'>
  onSaved: (preset: FilterPreset) => void
  onDeleted: () => void
}

export function FilterPresetDialog({ open, onOpenChange, preset, initial, onSaved, onDeleted }: Props) {
  if (!open) return null
  return <FilterPresetEditor key={preset?.id ?? 'new'} onOpenChange={onOpenChange} preset={preset} initial={initial} onSaved={onSaved} onDeleted={onDeleted} />
}

function FilterPresetEditor({ onOpenChange, preset, initial, onSaved, onDeleted }: Omit<Props, 'open'>) {
  const [name, setName] = useState(preset?.name ?? '')
  const create = useCreateFilterPreset()
  const update = useUpdateFilterPreset()
  const remove = useDeleteFilterPreset()
  const busy = create.isPending || update.isPending || remove.isPending

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data: FilterPresetInput = { name: name.trim(), ...initial }
    if (!data.name) return
    try {
      const saved = preset ? await update.mutateAsync({ id: preset.id, data }) : await create.mutateAsync(data)
      onSaved(saved)
      onOpenChange(false)
      toast.success(preset ? 'Preset updated.' : 'Preset saved.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not save preset.')
    }
  }

  async function deletePreset() {
    if (!preset || !window.confirm(`Delete preset “${preset.name}”?`)) return
    try {
      await remove.mutateAsync(preset.id)
      onDeleted()
      onOpenChange(false)
      toast.success('Preset deleted.')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete preset.')
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md w-[calc(100vw-2rem)] max-h-[calc(100dvh-2rem)] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{preset ? 'Edit filter preset' : 'Save filter preset'}</DialogTitle>
          <DialogDescription>This saves the current Filters choices. Search and safe view stay independent.</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-4">
          <label className="block space-y-1 text-sm font-medium" htmlFor="preset-name">
            <span>Name</span>
            <Input id="preset-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={60} required placeholder="My reading list" />
          </label>
          <div className="rounded-lg border border-border bg-muted/30 p-3 text-sm space-y-1">
            <p>Categories: {initial.categories.length ? initial.categories.join(', ') : 'All'}</p>
            <p>{initial.unread_only ? 'Unread only' : 'Read and unread'} · {initial.include_inactive ? 'Include inactive' : 'Active only'}</p>
            <p>Sort: {initial.sort_key.replaceAll('_', ' ')} ({initial.sort_dir === 'asc' ? 'ascending' : 'descending'})</p>
          </div>
          <DialogFooter>
            {preset && <Button type="button" variant="destructive" onClick={deletePreset} disabled={busy} className="sm:mr-auto">Delete</Button>}
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>Cancel</Button>
            <Button type="submit" disabled={busy || !name.trim()}>{preset ? 'Save changes' : 'Save preset'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
