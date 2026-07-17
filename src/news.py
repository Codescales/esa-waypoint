"""News ticker orchestrator.

Collects gaming/speedrun news from the configured sources (speedrun.com for
games in the current schedule + RSS feeds), upserts them into SQLite via the
repo, and prunes to a retention cap.

Designed as a seam: an IGDB fetcher can be added later behind Twitch OAuth env
vars without changing the schema or this signature.
"""

from __future__ import annotations

from typing import Iterable

from . import news_rss, news_speedrun


def collect_news(
    repo,
    schedule_game_names: Iterable[str],
    rss_feeds: Iterable[str],
    *,
    speedrun_top_n: int = 3,
    rss_max_per_feed: int = 10,
    max_items: int = 100,
) -> dict:
    """Fetch from all sources, upsert, prune. Returns a summary dict.

    `repo` must expose `upsert_news_items(list[dict]) -> int` and
    `prune_news(keep) -> int`.
    """
    items: list[dict] = []

    game_names = list(schedule_game_names)
    speedrun_items = news_speedrun.fetch_news(game_names, top_n=speedrun_top_n)
    items.extend(speedrun_items)

    feeds = [f for f in rss_feeds if (f or "").strip()]
    rss_items = news_rss.fetch_news(feeds, max_items_per_feed=rss_max_per_feed)
    items.extend(rss_items)

    inserted = repo.upsert_news_items(items)
    pruned = repo.prune_news(keep=max_items)

    return {
        "fetched": len(items),
        "speedrun": len(speedrun_items),
        "rss": len(rss_items),
        "inserted": inserted,
        "pruned": pruned,
        "games_checked": len(game_names),
        "feeds_checked": len(feeds),
    }
