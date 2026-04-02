import { BookMarked, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ThemeToggle } from './ThemeToggle'
import { useCheckAll } from '@/hooks/useItems'
import { toast } from 'sonner'

export function Header() {
  const checkAll = useCheckAll()

  function handleCheckAll() {
    checkAll.mutate(undefined, {
      onSuccess: (data) => {
        toast.success(`Checked ${data.checked} item(s)`, {
          description: `${data.results.filter((r) => r.new_latest_chapter).length} update(s) found.`,
        })
      },
      onError: () => toast.error('Check failed. Is the backend running?'),
    })
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-2 font-semibold text-foreground">
          <BookMarked className="h-5 w-5 text-primary" />
          <span className="hidden sm:inline">Chapter Tracker</span>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheckAll}
            disabled={checkAll.isPending}
            className="gap-2"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${checkAll.isPending ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">Check All</span>
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
  )
}
