import { AppLayout } from "@/components/layout/AppLayout";
import { ItemList } from "@/components/items/ItemList";

export function ItemsPage() {
  return (
    <AppLayout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold tracking-tight xl:text-3xl">
            My tracked content
          </h1>
          <p className="mt-1 text-sm text-muted-foreground xl:text-base">
            Monitor manga, web novels, and blogs for new chapters.
          </p>
        </div>
        <ItemList />
      </div>
    </AppLayout>
  );
}
