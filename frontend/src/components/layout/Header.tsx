import { RefreshCw, Eye, EyeOff, LogOut, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";
import { useCheckAll } from "@/hooks/useItems";
import { toast } from "sonner";
import { useAuth } from '@/auth/context'

export function Header() {
  const checkAll = useCheckAll();
  const auth = useAuth();

  function handleCheckAll() {
    checkAll.mutate(undefined, {
      onSuccess: (data) => {
        toast.success(`Checked ${data.checked} item(s)`, {
          description: `${data.results.filter((r) => r.new_latest_chapter).length} update(s) found.`,
        });
      },
      onError: () => toast.error("Check failed. Is the backend running?"),
    });
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-14 w-full max-w-[110rem] items-center justify-between px-2 sm:px-6 lg:px-8 2xl:px-10">
        <div className="flex items-center gap-2 font-semibold text-foreground">
          <img src="/icon-192.png" alt="" className="h-6 w-6" />
          <span className="hidden sm:inline">Chapter Tracker</span>
        </div>

        <div className="flex items-center gap-1 sm:gap-2">
          {auth.session?.is_admin && <select
            aria-label="Library account"
            value={auth.selectedUser || auth.session.id}
            onChange={(event) => auth.selectUser(event.target.value === auth.session?.id ? '' : event.target.value)}
            className="max-w-20 sm:max-w-32 rounded border bg-background px-1 py-1 text-xs"
          >
            {auth.users.map((user) => <option key={user.id} value={user.id}>{user.username}</option>)}
          </select>}
          <Button variant="outline" size="sm" onClick={() => auth.setSafeView(!auth.session?.safe_view_enabled).catch(() => toast.error('Could not change safe view.'))} title="Toggle safe view" className="gap-1">
            {auth.session?.safe_view_enabled ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            <span className="hidden sm:inline">{auth.session?.safe_view_enabled ? 'Safe view' : 'All entries'}</span>
          </Button>
          {auth.session?.is_admin && <Button variant="ghost" size="icon" title="Create invite link" onClick={async () => {
            try { await navigator.clipboard.writeText(await auth.createInvite()); toast.success('One-time invite link copied. Expires in 24 hours.'); }
            catch { toast.error('Could not create invite link.'); }
          }}><UserPlus className="h-4 w-4" /></Button>}
          <Button
            variant="outline"
            size="sm"
            onClick={handleCheckAll}
            disabled={checkAll.isPending}
            className="gap-2"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${checkAll.isPending ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">Check All</span>
          </Button>
          <ThemeToggle />
          <Button variant="ghost" size="icon" title="Sign out" onClick={() => auth.logout().catch(() => toast.error('Could not sign out.'))}><LogOut className="h-4 w-4" /></Button>
        </div>
      </div>
    </header>
  );
}
