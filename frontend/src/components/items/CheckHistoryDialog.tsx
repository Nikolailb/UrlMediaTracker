import { CheckCircle2, XCircle, Clock } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useCheckHistory } from '@/hooks/useItems'
import type { ItemRead } from '@/types/api'

interface CheckHistoryDialogProps {
  item: ItemRead | null
  onOpenChange: (open: boolean) => void
}

function formatTs(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function CheckHistoryDialog({ item, onOpenChange }: CheckHistoryDialogProps) {
  const open = item !== null
  const { data: logs, isLoading } = useCheckHistory(item?.id ?? null)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Check history</DialogTitle>
          <DialogDescription>
            Last 20 check results for{' '}
            <span className="font-medium">{item?.title ?? item?.original_url}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-96 overflow-y-auto space-y-1.5 pr-1">
          {isLoading && (
            <>
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} className="h-12 w-full rounded-lg" />
              ))}
            </>
          )}

          {!isLoading && logs?.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No checks have been run yet.
            </p>
          )}

          {logs?.map((log) => (
            <div
              key={log.id}
              className={`flex items-start gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                log.success
                  ? 'border-emerald-500/20 bg-emerald-500/5'
                  : 'border-destructive/20 bg-destructive/5'
              }`}
            >
              {log.success ? (
                <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0 text-emerald-500" />
              ) : (
                <XCircle className="h-4 w-4 mt-0.5 shrink-0 text-destructive" />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">
                    {log.success
                      ? log.new_latest_chapter
                        ? `New chapter: ${log.new_latest_chapter}`
                        : 'Up to date'
                      : 'Failed'}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                    <Clock className="h-3 w-3" />
                    {formatTs(log.checked_at)}
                  </span>
                </div>
                {log.error_message && (
                  <p className="text-xs text-destructive mt-0.5 truncate" title={log.error_message}>
                    {log.error_message}
                  </p>
                )}
                {log.success && log.previous_latest_chapter && log.new_latest_chapter && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {log.previous_latest_chapter} → {log.new_latest_chapter}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}
