import { AppLayout } from '@/components/layout/AppLayout'
import { ItemList } from '@/components/items/ItemList'

export function ItemsPage() {
  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">My tracked content</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Monitor manga, web novels, and blogs for new chapters.
          </p>
        </div>
        <ItemList />
      </div>
    </AppLayout>
  )
}
