import { useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useUpdateItem } from "@/hooks/useItems";
import { toast } from "sonner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CheckStrategy, ItemRead } from "@/types/api";
import { ITEM_CATEGORIES } from "@/types/api";
import { cn } from "@/lib/utils";

interface EditItemDialogProps {
  item: ItemRead | null;
  onOpenChange: (open: boolean) => void;
}

type Tab = "general" | "detection";

const STRATEGIES: {
  value: CheckStrategy;
  label: string;
  description: string;
}[] = [
  {
    value: "INCREMENTAL_PROBE",
    label: "Sequential URL probing",
    description:
      "Builds chapter URLs from a template and probes them numerically.",
  },
  {
    value: "TOC_SCRAPER",
    label: "Table of contents scan",
    description: "Scrapes the ToC page for chapter links. Requires a ToC URL.",
  },
  {
    value: "TOC_THEN_PROBE",
    label: "ToC first, then probe",
    description:
      "Tries ToC scan first; falls back to sequential probing if it finds nothing.",
  },
];

export function EditItemDialog({ item, onOpenChange }: EditItemDialogProps) {
  const open = item !== null;
  const [tab, setTab] = useState<Tab>("general");
  const [title, setTitle] = useState(item?.title ?? "");
  const [manualRegex, setManualRegex] = useState(item?.chapter_regex ?? "");
  const [interval, setInterval] = useState(
    String(item?.check_interval_min ?? 60),
  );
  const [currentChapter, setCurrentChapter] = useState(
    item?.current_chapter ?? "",
  );
  const [isActive, setIsActive] = useState(item?.is_active ?? true);
  const [tocUrl, setTocUrl] = useState(item?.toc_url ?? "");
  const [category, setCategory] = useState(item?.category ?? "");
  const [checkStrategy, setCheckStrategy] = useState<CheckStrategy>(
    item?.check_strategy ?? "INCREMENTAL_PROBE",
  );

  const update = useUpdateItem();

  function handleSubmit() {
    if (!item) return;
    update.mutate(
      {
        id: item.id,
        data: {
          title: title.trim() || null,
          manual_regex: manualRegex.trim() || null,
          check_interval_min: parseInt(interval) || 60,
          current_chapter: currentChapter.trim() || null,
          is_active: isActive,
          toc_url: tocUrl.trim() || null,
          category: category || null,
          check_strategy: checkStrategy,
        },
      },
      {
        onSuccess: () => {
          toast.success("Item updated.");
          onOpenChange(false);
        },
        onError: (err) => toast.error(err.message),
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col max-h-[calc(100dvh-4rem)]">
        <DialogHeader className="shrink-0">
          <DialogTitle>Edit item</DialogTitle>
          <DialogDescription>
            Update details for this tracked item.
          </DialogDescription>
        </DialogHeader>

        {/* Tab bar */}
        <div className="shrink-0 flex gap-1 border-b border-border -mx-6 px-6">
          {(["general", "detection"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                "px-3 py-2 text-sm font-medium capitalize transition-colors",
                "border-b-2 -mb-px",
                tab === t
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Scrollable form body */}
        <div className="overflow-y-auto flex-1 -mx-6 px-6 py-4">
          {tab === "general" && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="edit-title">Title</Label>
                <Input
                  id="edit-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-chapter">Current chapter</Label>
                <Input
                  id="edit-chapter"
                  value={currentChapter}
                  onChange={(e) => setCurrentChapter(e.target.value)}
                  placeholder="e.g. 183"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-category">
                  Category{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Select
                  value={category}
                  onValueChange={(v) => setCategory(v === "__none__" ? "" : v)}
                >
                  <SelectTrigger id="edit-category">
                    <SelectValue placeholder="No category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">No category</SelectItem>
                    {ITEM_CATEGORIES.map((c) => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-interval">Check interval (minutes)</Label>
                <Input
                  id="edit-interval"
                  type="number"
                  min="5"
                  value={interval}
                  onChange={(e) => setInterval(e.target.value)}
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  id="edit-active"
                  type="checkbox"
                  checked={isActive}
                  onChange={(e) => setIsActive(e.target.checked)}
                  className="h-4 w-4 rounded border-border accent-primary"
                />
                <Label htmlFor="edit-active">Active (check for updates)</Label>
              </div>
            </div>
          )}

          {tab === "detection" && (
            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="edit-strategy">Check strategy</Label>
                <Select
                  value={checkStrategy}
                  onValueChange={(v) => setCheckStrategy(v as CheckStrategy)}
                >
                  <SelectTrigger id="edit-strategy">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STRATEGIES.map((s) => (
                      <SelectItem key={s.value} value={s.value}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-[11px] text-muted-foreground leading-snug">
                  {
                    STRATEGIES.find((s) => s.value === checkStrategy)
                      ?.description
                  }
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-toc">
                  Table of contents URL{" "}
                  <span className="text-muted-foreground font-normal">
                    (optional)
                  </span>
                </Label>
                <Input
                  id="edit-toc"
                  placeholder="https://example.com/series/my-title/"
                  value={tocUrl}
                  onChange={(e) => setTocUrl(e.target.value)}
                />
                <p className="text-[11px] text-muted-foreground leading-snug">
                  Required for <em>ToC scan</em> strategies. The page must list
                  chapter links matching the tracker URL template.
                </p>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="edit-regex">
                  Chapter regex override{" "}
                  <span className="text-muted-foreground font-normal">
                    (one capture group)
                  </span>
                </Label>
                <Input
                  id="edit-regex"
                  value={manualRegex}
                  onChange={(e) => setManualRegex(e.target.value)}
                  placeholder="chapter-(\d+)"
                  className="font-mono text-xs"
                />
                <p className="text-[11px] text-muted-foreground leading-snug">
                  Overrides the auto-detected URL pattern. Leave blank to keep
                  the detected pattern.
                </p>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="shrink-0 pt-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={update.isPending}>
            {update.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Save changes
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
