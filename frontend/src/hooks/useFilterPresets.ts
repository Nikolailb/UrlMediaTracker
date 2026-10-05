import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { del, get, post, put } from '@/api/client'
import type { FilterPreset, FilterPresetInput } from '@/types/api'

const KEY = ['filter-presets'] as const

export function useFilterPresets() {
  return useQuery({ queryKey: KEY, queryFn: () => get<FilterPreset[]>('/filter-presets') })
}

export function useCreateFilterPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (data: FilterPresetInput) => post<FilterPreset>('/filter-presets', data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useUpdateFilterPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FilterPresetInput }) => put<FilterPreset>(`/filter-presets/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteFilterPreset() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => del(`/filter-presets/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}
