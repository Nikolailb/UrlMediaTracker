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
