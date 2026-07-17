"""Tests for the news ticker: fetchers, repo methods, and routes."""

from datetime import datetime, timezone

import pytest

from src import news as news_mod
from src import news_rss, news_speedrun


# ── RSS fetcher ────────────────────────────────────────────────────────────

def test_rss_strip_html():
    assert news_rss._strip_html("<p>Big <b>news</b></p>") == "Big news"
    assert news_rss._strip_html("plain") == "plain"


def test_rss_entry_published_none():
    class E:
        pass
    assert news_rss._entry_published(E()) is None


def test_rss_fetch_feed_parses(monkeypatch):
    sample = (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>GameSpot</title>'
        '<item><title>New game announced</title><link>http://x/1</link>'
        "<guid>g1</guid><description>&lt;p&gt;Big news&lt;/p&gt;</description>"
        "<pubDate>Wed, 15 Jul 2026 12:00:00 GMT</pubDate></item>"
        "</channel></rss>"
    )
    import feedparser

    parsed = feedparser.parse(sample)
    monkeypatch.setattr(news_rss.feedparser, "parse", lambda url: parsed)
    items = news_rss.fetch_feed("http://x")
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "New game announced"
    assert it["url"] == "http://x/1"
    assert it["category"] == "news"
    assert it["source"] == "rss"
    assert it["source_label"] == "GameSpot"
    assert it["dedupe_key"] == "rss:g1"


def test_rss_fetch_news_swallows_errors(monkeypatch):
    def boom(url):
        raise RuntimeError("network down")

    monkeypatch.setattr(news_rss.feedparser, "parse", boom)
    assert news_rss.fetch_news(["http://x"]) == []


# ── speedrun fetcher ───────────────────────────────────────────────────────

def test_speedrun_fmt_time():
    assert news_speedrun._fmt_time(None) == ""
    assert news_speedrun._fmt_time(90) == "1:30"
    assert news_speedrun._fmt_time(3661) == "1:01:01"


def test_speedrun_fetch_for_game(monkeypatch):
    monkeypatch.setattr(
        news_speedrun.src_api, "search_src_game",
        lambda name: {"id": "g1", "names": {"international": "Super Metroid"}},
    )

    def fake_get(path, _retry=True):
        return {
            "data": [
                {
                    "id": "r1",
                    "place": 1,
                    "weblink": "http://sr/r1",
                    "times": {"primary_t": 2483},
                    "category": {"data": {"name": "Any%"}},
                    "players": {"data": [{"names": {"international": "Zoast"}}]},
                    "status": {"verify-date": "2026-07-15T12:00:00Z"},
                },
            ]
        }

    monkeypatch.setattr(news_speedrun.src_api, "src_get", fake_get)
    items = news_speedrun.fetch_for_game("Super Metroid")
    assert len(items) == 1
    it = items[0]
    assert it["category"] == "wr"
    assert "New WR" in it["title"]
    assert "Super Metroid" in it["title"]
    assert "Zoast" in it["title"]
    assert it["dedupe_key"] == "speedrun:r1"
    assert it["published_at"].year == 2026


def test_speedrun_unresolved_game(monkeypatch):
    monkeypatch.setattr(news_speedrun.src_api, "search_src_game", lambda name: None)
    assert news_speedrun.fetch_for_game("Nonexistent") == []


def test_speedrun_fetch_news_dedupes_names(monkeypatch):
    calls = []
    monkeypatch.setattr(
        news_speedrun, "fetch_for_game",
        lambda name, top_n=3: calls.append(name) or [],
    )
    news_speedrun.fetch_news(["Portal", "portal", "  Portal  ", "Celeste"])
    assert len(calls) == 2  # Portal (deduped) + Celeste


# ── repo methods ───────────────────────────────────────────────────────────

def test_repo_upsert_and_list(repo):
    inserted = repo.upsert_news_items([
        {"source": "rss", "category": "news", "source_label": "X",
         "title": "A", "url": "http://a", "summary": "", "published_at": None,
         "dedupe_key": "rss:a"},
        {"source": "speedrun", "category": "wr", "source_label": "speedrun.com",
         "title": "B", "url": "http://b", "summary": "",
         "published_at": datetime(2026, 7, 15, tzinfo=timezone.utc),
         "dedupe_key": "speedrun:b"},
    ])
    assert inserted == 2
    # idempotent
    assert repo.upsert_news_items([{"source": "rss", "dedupe_key": "rss:a", "title": "A"}]) == 0
    items = repo.list_news()
    titles = {i.title for i in items}
    assert titles == {"A", "B"}


def test_repo_list_ordered_by_recency(repo):
    repo.upsert_news_items([
        {"source": "rss", "dedupe_key": "rss:old", "title": "old",
         "published_at": datetime(2020, 1, 1, tzinfo=timezone.utc)},
        {"source": "rss", "dedupe_key": "rss:new", "title": "new",
         "published_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
    ])
    items = repo.list_news()
    assert items[0].title == "new"


def test_repo_prune(repo):
    repo.upsert_news_items([
        {"source": "rss", "dedupe_key": f"rss:{i}", "title": str(i),
         "published_at": datetime(2020, 1, 1 + i, tzinfo=timezone.utc)}
        for i in range(5)
    ])
    deleted = repo.prune_news(keep=2)
    assert deleted == 3
    assert len(repo.list_news()) == 2


def test_repo_schedule_game_names(repo, db_path):
    # empty schedule initially
    assert repo.schedule_game_names() == []


# ── orchestrator ───────────────────────────────────────────────────────────

def test_collect_news(repo, monkeypatch):
    monkeypatch.setattr(
        news_mod.news_speedrun, "fetch_news",
        lambda names, top_n=3: [{"source": "speedrun", "dedupe_key": "speedrun:1", "title": "WR"}],
    )
    monkeypatch.setattr(
        news_mod.news_rss, "fetch_news",
        lambda feeds, max_items_per_feed=10: [{"source": "rss", "dedupe_key": "rss:1", "title": "News"}],
    )
    result = news_mod.collect_news(repo, ["Portal"], ["http://feed"])
    assert result["inserted"] == 2
    assert result["speedrun"] == 1
    assert result["rss"] == 1
    assert len(repo.list_news()) == 2


# ── routes ─────────────────────────────────────────────────────────────────

def test_news_route_returns_items(client, seeded_db):
    from web.backend.repo_sqlite import SqliteIncentiveRepo
    SqliteIncentiveRepo(seeded_db).upsert_news_items([
        {"source": "rss", "category": "news", "source_label": "X",
         "title": "Route test item", "url": "http://x", "dedupe_key": "rss:route"},
    ])
    resp = client.get("/api/news")
    assert resp.status_code == 200
    titles = [i["title"] for i in resp.json()]
    assert "Route test item" in titles


def test_news_route_requires_auth(unauth_client):
    resp = unauth_client.get("/api/news")
    assert resp.status_code == 401


def test_sync_news_endpoint(client, monkeypatch):
    monkeypatch.setattr(
        news_mod.news_speedrun, "fetch_news", lambda names, top_n=3: []
    )
    monkeypatch.setattr(
        news_mod.news_rss, "fetch_news", lambda feeds, max_items_per_feed=10: [
            {"source": "rss", "dedupe_key": "rss:sync1", "title": "Synced"}
        ]
    )
    resp = client.post("/api/admin/sync/news")
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"
