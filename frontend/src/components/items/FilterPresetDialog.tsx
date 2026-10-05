import { useState, type FormEvent } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ITEM_CATEGORIES } from '@/types/api'
import type { FilterPreset, FilterPresetInput, ItemCategory } from '@/types/api'
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
  const [categories, setCategories] = useState<ItemCategory[]>(preset?.categories ?? initial.categories)
  const [unreadOnly, setUnreadOnly] = useState(preset?.unread_only ?? initial.unread_only)
  const [includeInactive, setIncludeInactive] = useState(preset?.include_inactive ?? initial.include_inactive)
  const create = useCreateFilterPreset()
  const update = useUpdateFilterPreset()
  const remove = useDeleteFilterPreset()
  const busy = create.isPending || update.isPending || remove.isPending

  function toggleCategory(category: ItemCategory) {
    setCategories((previous) => previous.includes(category)
      ? previous.filter((value) => value !== category)
      : [...previous, category])
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data: FilterPresetInput = { name: name.trim(), categories, unread_only: unreadOnly, include_inactive: includeInactive }
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
          <DialogDescription>Choose categories and status. Search, sort, and safe view stay independent.</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-4">
          <label className="block space-y-1 text-sm font-medium" htmlFor="preset-name">
            <span>Name</span>
            <Input id="preset-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={60} required placeholder="My reading list" />
          </label>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Categories <span className="font-normal text-muted-foreground">(none means all)</span></legend>
            <div className="grid grid-cols-2 gap-2">
              {ITEM_CATEGORIES.map((category) => (
                <label key={category} className="flex items-center gap-2 text-sm min-w-0">
                  <input type="checkbox" checked={categories.includes(category)} onChange={() => toggleCategory(category)} className="accent-primary" />
                  <span className="truncate">{category}</span>
                </label>
              ))}
            </div>
          </fieldset>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={unreadOnly} onChange={(event) => setUnreadOnly(event.target.checked)} className="accent-primary" /> Unread only
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={includeInactive} onChange={(event) => setIncludeInactive(event.target.checked)} className="accent-primary" /> Include inactive items
          </label>
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
