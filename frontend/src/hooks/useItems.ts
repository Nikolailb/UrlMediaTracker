import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { itemsApi } from '@/api/items'
import type { ItemCreate, ItemUpdate, MarkReadRequest } from '@/types/api'

const ITEMS_KEY = ['items'] as const

export function useItems(params?: { active_only?: boolean }) {
  return useQuery({
    queryKey: [...ITEMS_KEY, params],
    queryFn: () => itemsApi.list(params),
  })
}

export function useCreateItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: ItemCreate) => itemsApi.create(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useUpdateItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ItemUpdate }) =>
      itemsApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useDeleteItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => itemsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useMarkRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MarkReadRequest }) =>
      itemsApi.markRead(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useMarkCaughtUp() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, chapter }: { id: string; chapter: string }) =>
      itemsApi.markRead(id, { chapter }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useCheckItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => itemsApi.check(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useCheckAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => itemsApi.checkAll(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useCheckHistory(itemId: string | null) {
  return useQuery({
    queryKey: ['check-history', itemId],
    queryFn: () => itemsApi.history(itemId!),
    enabled: itemId !== null,
  })
}

export function useBulkDelete() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => itemsApi.bulkDelete(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useBulkPause() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => itemsApi.bulkPause(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useBulkResume() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (ids: string[]) => itemsApi.bulkResume(ids),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

export function useImportItems() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (records: unknown[]) => itemsApi.importItems(records),
    onSuccess: () => qc.invalidateQueries({ queryKey: ITEMS_KEY }),
  })
}

