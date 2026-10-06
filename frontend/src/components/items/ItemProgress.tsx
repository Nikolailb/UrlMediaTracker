import { chapterToFloat } from "@/lib/utils";
import type { ItemRead } from "@/types/api";
import { hasAmbiguousChapterIds } from '@/lib/chapterUrls'

interface ItemProgressProps {
  item: ItemRead;
  className?: string;
}

interface ChapterLinkProps {
  chapter: string | null;
  href: string | null;
}

function ChapterLink({ chapter, href }: ChapterLinkProps) {
  if (!chapter) return <span className="text-muted-foreground">—</span>;
  if (!href) return <span title="Exact chapter link unavailable; open the series ToC">{chapter}</span>;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="transition-colors hover:text-primary hover:underline underline-offset-2"
      title={`Open chapter ${chapter}`}
    >
      {chapter}
    </a>
  );
}

function chapterUrl(
  template: string | null,
  chapter: string | null,
): string | null {
  if (!template?.includes('{n}') || !chapter) return null;
  if (hasAmbiguousChapterIds(template)) return null;
  return template.replace("{n}", encodeURIComponent(chapter));
}

export function ItemProgress({ item, className }: ItemProgressProps) {
  const current = item.current_chapter;
  const latest = item.latest_chapter;
  // REQ-011: show a start link without claiming the first chapter was read.
  const firstUnread = (!current || current === '0') &&
    latest !== null && Number.isFinite(Number(latest)) && Number(latest) >= 1;
  const shownCurrent = firstUnread ? '1' : current;

  if (!current && !latest) {
    return <span className="text-xs text-muted-foreground">No data</span>;
  }

  const currentF = chapterToFloat(current);
  const latestF = chapterToFloat(latest);
  const hasUnread = item.has_unread === true;

  const pct =
    latestF > 0 && currentF >= 0
      ? Math.min(100, Math.round((currentF / latestF) * 100))
      : null;

  const currentHref = (shownCurrent === '1' && item.first_chapter_url) || chapterUrl(item.url_template, shownCurrent);
  const latestHref = item.latest_chapter_url || chapterUrl(item.url_template, latest);

  return (
    <div className={`space-y-1 ${className ?? ""}`}>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium tabular-nums">
          <ChapterLink chapter={shownCurrent} href={currentHref} />
          {" / "}
          <ChapterLink chapter={latest} href={latestHref} />
        </span>
        {hasUnread && (
          <span
            className="inline-flex h-2 w-2 rounded-full bg-primary animate-pulse"
            title="Unread chapters available"
          />
        )}
      </div>
      {pct !== null && (
        <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${hasUnread ? "bg-primary" : "bg-muted-foreground/40"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}
