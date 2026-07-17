"use client";

import { useNews } from "@/lib/hooks";
import { NewsItem } from "@/lib/api";

function categoryLabel(item: NewsItem): { text: string; cls: string } {
  switch (item.category) {
    case "wr":
      return { text: "WR", cls: "pill-approve" };
    case "new_run":
      return { text: "RUN", cls: "pill-next" };
    default:
      return { text: "NEWS", cls: "pill-todo" };
  }
}

function TickerItem({ item }: { item: NewsItem }) {
  const cat = categoryLabel(item);
  return (
    <a
      href={item.url || undefined}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-2 px-4 no-underline hover:text-brand transition-colors"
      title={item.summary || item.title}
    >
      <span className={`pill ${cat.cls}`}>{cat.text}</span>
      <span className="text-foreground">{item.title}</span>
      {item.source_label ? (
        <span className="text-muted text-xs">· {item.source_label}</span>
      ) : null}
      <span className="text-border select-none" aria-hidden>
        •
      </span>
    </a>
  );
}

export default function NewsTicker() {
  const { news } = useNews();

  if (!news.length) return null;

  // Duplicate the list once so the -50% translate loops seamlessly.
  const doubled = [...news, ...news];
  // Scale duration with item count so long lists don't scroll too fast.
  const duration = Math.max(30, news.length * 6);

  return (
    <div
      className="bg-surface border-b border-border text-sm overflow-hidden"
      role="marquee"
      aria-label="Gaming and speedrun news"
    >
      <div className="ticker-viewport relative overflow-hidden whitespace-nowrap py-2">
        <div
          className="ticker-track"
          style={{ ["--ticker-duration" as string]: `${duration}s` }}
        >
          {doubled.map((item, i) => (
            <TickerItem key={`${item.id}-${i}`} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
