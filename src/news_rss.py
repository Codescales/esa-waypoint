"""Gaming-news RSS fetcher for the news ticker.

Parses a list of RSS/Atom feed URLs with `feedparser` and maps entries to
news-item dicts (category="news"). Errors on individual feeds/entries are
swallowed so one bad feed doesn't abort the refresh.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import feedparser


SOURCE = "rss"


def _entry_published(entry) -> datetime | None:
    parsed = getattr(entry, "published_parsed", None) or getattr(
        entry, "updated_parsed", None
    )
    if not parsed:
        return None
    try:
        # feedparser returns a time.struct_time in UTC
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _feed_label(parsed_feed, url: str) -> str:
    title = getattr(parsed_feed.feed, "title", "") if parsed_feed.feed else ""
    if title:
        return str(title)
    # fall back to the host
    try:
        from urllib.parse import urlparse

        return urlparse(url).netloc or url
    except Exception:
        return url


def fetch_feed(url: str, max_items: int = 10) -> list[dict]:
    """Fetch and parse a single feed. Returns news-item dicts."""
    parsed = feedparser.parse(url)
    if getattr(parsed, "bozo", False) and not parsed.entries:
        return []
    label = _feed_label(parsed, url)
    items: list[dict] = []
    for entry in parsed.entries[:max_items]:
        title = getattr(entry, "title", "") or ""
        link = getattr(entry, "link", "") or ""
        if not title or not link:
            continue
        summary = getattr(entry, "summary", "") or ""
        # feedparser summaries may contain HTML; keep it short and stripped
        summary = _strip_html(summary)[:280]
        dedupe = getattr(entry, "id", "") or link
        items.append({
            "source": SOURCE,
            "source_label": label,
            "category": "news",
            "title": title.strip(),
            "url": link,
            "summary": summary,
            "published_at": _entry_published(entry),
            "dedupe_key": f"{SOURCE}:{dedupe}",
        })
    return items


def _strip_html(text: str) -> str:
    import re

    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_news(feed_urls: Iterable[str], max_items_per_feed: int = 10) -> list[dict]:
    """Fetch news across all configured feeds. Swallows per-feed errors."""
    items: list[dict] = []
    for url in feed_urls:
        url = (url or "").strip()
        if not url:
            continue
        try:
            items.extend(fetch_feed(url, max_items=max_items_per_feed))
        except Exception:
            continue
    return items
