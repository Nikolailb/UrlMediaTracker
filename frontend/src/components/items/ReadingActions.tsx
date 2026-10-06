import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { itemsApi } from '@/api/items'
import { useMarkRead } from '@/hooks/useItems'
import type { ItemRead } from '@/types/api'
import { toast } from 'sonner'

export function ReadingActions({ item, compact = false }: { item: ItemRead; compact?: boolean }) {
  const markRead = useMarkRead()
  const [opening, setOpening] = useState(false)
  const canOpen = Boolean(item.url_template?.includes('{n}') && item.has_unread)

  async function openNext() {
    // Open synchronously so browsers do not block the tab after the API response.
    const readingTab = window.open('', '_blank')
    if (readingTab) readingTab.opener = null
    setOpening(true)
    try {
      const next = await itemsApi.next(item.id)
      if (next.next_url) {
        if (readingTab) readingTab.location.href = next.next_url
        else window.open(next.next_url, '_blank', 'noopener,noreferrer')
      } else {
        readingTab?.close()
        toast.info(next.message)
      }
    } catch {
      readingTab?.close()
      toast.error('Could not open next chapter.')
    } finally {
      setOpening(false)
    }
  }

  async function markNext() {
    try {
      const next = await itemsApi.next(item.id)
      if (next.next_chapter) {
        await markRead.mutateAsync({ id: item.id, data: { chapter: next.next_chapter } })
        toast.success(`Marked chapter ${next.next_chapter} as read.`)
      } else toast.info(next.message)
    } catch { toast.error('Could not mark next chapter as read.') }
  }

  return <div className={`flex flex-wrap gap-2 ${compact ? 'mt-2' : ''}`}>
    <Button size="sm" variant="outline" onClick={openNext} disabled={!canOpen || opening} title={canOpen ? 'Open the next unread chapter' : 'Requires unread chapters and a chapter URL pattern'}>Open next</Button>
    <Button size="sm" variant="outline" onClick={markNext} disabled={!canOpen || markRead.isPending} title={canOpen ? 'Mark the next chapter as read' : 'Requires unread chapters and a chapter URL pattern'}>Mark read</Button>
  </div>
}
