import type { ItemStatus } from '@/types/api'

export const statusLabel: Record<ItemStatus, string> = {
  ONGOING: 'Ongoing',
  PAUSED: 'Paused',
  COMPLETED: 'Completed',
  FINISHED: 'Finished',
}

export function caughtUp(current: string | null, latest: string | null): boolean {
  if (!current?.trim() || !latest?.trim()) return false
  const numeric = /^(?:\d+)(?:\.\d+)?$/
  if (numeric.test(current) && numeric.test(latest)) return Number(current) >= Number(latest)
  return false
}
