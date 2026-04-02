import { del, get, patch, post } from './client'
import type {
  CheckAllResult,
  CheckResult,
  ItemCreate,
  ItemRead,
  ItemUpdate,
  MarkReadRequest,
  NextChapterResponse,
} from '@/types/api'

export const itemsApi = {
  list: (params?: { user_id?: string; active_only?: boolean }) => {
    const qs = new URLSearchParams()
    if (params?.user_id) qs.set('user_id', params.user_id)
    if (params?.active_only) qs.set('active_only', 'true')
    const query = qs.toString()
    return get<ItemRead[]>(`/items${query ? `?${query}` : ''}`)
  },

  get: (id: string) => get<ItemRead>(`/items/${id}`),

  create: (data: ItemCreate) => post<ItemRead>('/items', data),

  update: (id: string, data: ItemUpdate) => patch<ItemRead>(`/items/${id}`, data),

  delete: (id: string) => del(`/items/${id}`),

  markRead: (id: string, data: MarkReadRequest) =>
    post<ItemRead>(`/items/${id}/mark-read`, data),

  next: (id: string) => get<NextChapterResponse>(`/items/${id}/next`),

  check: (id: string) => post<CheckResult>(`/items/${id}/check`),

  checkAll: () => post<CheckAllResult>('/items/check-all'),
}
