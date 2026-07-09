"""Search GDQ tracker and speedrun.com for incentive ideas for a given game.

Fetches bid data from recent GDQ events and filters by game name/keywords.
Also searches speedrun.com for category upgrade suggestions.
Returns incentive ideas categorized as Reward, Poll-Bid War, or Target.
"""

import json
import re
import sys
import urllib.request

from .src_api import (
    SrcApiError,
    search_src_game,
    fetch_src_categories,
    fetch_src_subcategories,
    fetch_category_wr,
    fetch_game_records,
)

GDQ_EVENTS = [
    ("SGDQ 2025", "sgdq2025"),
    ("AGDQ 2026", "AGDQ2026"),
    ("Frost Fatales 2026", "frostfatales2026"),
    ("AGDQ 2025", "AGDQ2025"),
    ("SGDQ 2024", "SGDQ2024"),
    ("Frost Fatales 2025", "FrostFatales2025"),
    ("SGDQ 2023", "SGDQ2023"),
    ("AGDQ 2024", "AGDQ2024"),
    ("SGDQ 2022", "sgdq2022"),
    ("AGDQ 2023", "AGDQ2023"),
    ("Frost Fatales 2024", "FrostFatales2024"),
    ("Games Done Queer 2025", "GDQueer"),
    # Additions to cover niche games
    ("Flame Fatales 2025", "flamefatales2025"),
    ("Flame Fatales 2024", "flamefatales2024"),
    ("Flame Fatales 2023", "flamefatales2023"),
    ("Flame Fatales 2022", "flamefatales2022"),
    ("Flame Fatales 2021", "flamefatales2021"),
    ("Fleet Fatales 2020", "fleetfatales2020"),
    ("Frost Fatales 2023", "FrostFatales2023"),
    ("Frost Fatales 2022", "frostfatales2022"),
    ("AGDQ 2022", "AGDQ2022"),
    ("SGDQ 2021", "SGDQ2021"),
    ("Back to Black 2026", "BTB26"),
    ("Disaster Relief Done Quick 2024", "DRDQ2024"),
    ("GDQX 2025", "GDQX2025"),
    ("GDQX 2024", "GDQX2024"),
    ("GDQX 2023", "GDQX2023"),
    ("Back to Black 2025", "BTB2025"),
]


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&mdash;", "—").replace("&quot;", '"').replace("&#39;", "'")
    text = re.sub(r"&amp;", "&", text)
    return re.sub(r"\s+", " ", text).strip()


def fetch_event_bids(event_slug: str) -> list[dict]:
    """Fetch and parse all bids for a GDQ event from the tracker HTML.

    Returns only parent bids, not sub-bid options. Each bid and its
    sub-options form a group in the HTML, with the parent identified by
    having "Show Options"/"Hide Options" buttons nearby.
    """
    url = f"https://tracker.gamesdonequick.com/tracker/bids/{event_slug}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Gecko/20100101 Firefox/115.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8")
    except Exception:
        return []

    links = list(re.finditer(r'href="/tracker/bid/(\d+)">\s*([^<]+?)\s*</a>', html))
    all_bids = []

    for i, m in enumerate(links):
        bid_id = m.group(1)
        name = m.group(2).strip()
        next_start = links[i + 1].start() if i + 1 < len(links) else len(html)
        chunk = html[m.start():next_start]

        is_choice = "Show Options" in chunk or "Hide Options" in chunk

        cells = re.findall(r"<td[^>]*>(.*?)</td>", chunk, re.DOTALL)
        run = _clean_html(cells[0]) if len(cells) >= 1 else ""
        desc = _clean_html(cells[1]) if len(cells) >= 2 else ""
        amount = _clean_html(cells[2]) if len(cells) >= 3 else ""

        inside_hidden = _is_inside_hidden_div(html, m.start())

        all_bids.append({
            "id": bid_id,
            "name": name,
            "run": run,
            "description": desc,
            "amount": amount,
            "is_choice": is_choice,
            "inside_hidden": inside_hidden,
            "event": event_slug,
        })

    return [b for b in all_bids if b["is_choice"] or not b["inside_hidden"]]


def _is_inside_hidden_div(html: str, pos: int) -> bool:
    """Check if a position in the HTML is inside a display:none div."""
    before = html[:pos]
    last_dn = before.rfind('style="display:none"')
    if last_dn < 0:
        last_dn = before.rfind("display:none")
    if last_dn < 0:
        return False
    last_close = before.rfind("</div>")
    return last_dn > last_close


def _normalize_text(text: str) -> str:
    """Normalize for matching: lowercase, accents, HTML entities, &→and, collapse whitespace."""
    text = text.lower()
    # Decode common HTML entities
    text = re.sub(r"&#x27;|&#39;", "'", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&mdash;", "—", text)
    # Decode numeric HTML entities for common chars
    text = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), text)
    # Normalize accents
    text = text.replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
    text = text.replace("à", "a").replace("â", "a").replace("ä", "a")
    text = text.replace("ù", "u").replace("û", "u").replace("ü", "u")
    text = text.replace("ô", "o").replace("ö", "o")
    text = text.replace("î", "i").replace("ï", "i")
    text = text.replace("ç", "c")
    # Replace "&" with "and"
    text = text.replace("&", " and ")
    # Strip/replace punctuation
    text = re.sub(r"[:\-\u2014\u2013\'\"]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# Words too generic to discriminate games — proven to cause over-matching in eval
GENERIC_WORDS = {
    "super", "world", "2d", "3d", "hd", "dx", "deluxe",
    "remake", "remaster", "remastered",
    "edition", "version", "collection", "pack",
    "definitive", "ultimate", "classic",
    "anniversary", "birthday",
    "plus", "alpha", "beta", "omega",
    "online", "multiplayer",
    "demo", "trial", "sample",
    "mini", "micro",
    "legacy", "chronicle", "chronicles",
    "mania",
    "epic",
    "metal",
    "dawn",
    "mansion",
    "temple",
    "castle",
    "project",
    "dark",
    "story",
}


def _game_keywords(game_name: str) -> dict:
    """Extract keywords from a game name for matching against bid run names.

    Returns:
        normalized: fully normalized game name
        meaningful: set of keywords that are not generic
    """
    normalized = _normalize_text(game_name)
    words = normalized.split()
    meaningful = {w for w in words if len(w) > 3 and w not in GENERIC_WORDS}
    return {"normalized": normalized, "meaningful": meaningful, "words": words}


def search_bids_for_game(bids: list[dict], game_name: str) -> list[dict]:
    """Filter bids to those matching the given game name/keywords, with confidence.

    Uses normalized text for matching (accents stripped, HTML entities decoded,
    & → and). Returns exact, franchise, and keyword-level matches.
    """
    kw = _game_keywords(game_name)
    normalized = kw["normalized"]
    meaningful = kw["meaningful"]

    matches = []
    for bid in bids:
        run_norm = _normalize_text(bid["run"])

        if normalized in run_norm:
            matches.append({**bid, "score": 5, "confidence": "exact"})
        elif meaningful and any(w in run_norm for w in meaningful):
            matches.append({**bid, "score": 3, "confidence": "keyword"})

    matches.sort(key=lambda b: -b["score"])
    return matches


def _categorize_bid(bid: dict) -> str:
    """Categorize a bid as Reward, Poll-Bid War, or Target."""
    if bid.get("is_choice"):
        return "Poll-Bid War"
    name_lower = bid["name"].lower()
    if "choice" in name_lower or "pick" in name_lower or "select" in name_lower:
        return "Poll-Bid War"
    desc_lower = bid["description"].lower()
    if "if met" in desc_lower or "if this is met" in desc_lower:
        return "Target"
    if "upgrade" in name_lower or "bonus" in name_lower or "add" in name_lower:
        return "Target"
    if "watch" in name_lower or "exhibition" in name_lower or "showcase" in name_lower:
        return "Target"
    return "Reward"


def find_category_upgrades(
    game_name: str,
    current_category: str = "",
    current_estimate_minutes: int = 0,
    max_delta_minutes: int = 20,
) -> dict:
    """Search speedrun.com for category upgrade suggestions.

    Returns categories with world record times that are:
    - Longer than the current category (upgrades)
    - Within max_delta_minutes of the current estimate
    """
    results = {
        "game": game_name,
        "current_category": current_category,
        "current_estimate_minutes": current_estimate_minutes,
        "src_game": None,
        "upgrades": [],
    }

    game = search_src_game(game_name)
    if not game:
        return results

    results["src_game"] = {
        "id": game["id"],
        "name": game.get("names", {}).get("international", game_name),
        "abbreviation": game.get("abbreviation", ""),
        "weblink": game.get("weblink", ""),
    }

    categories = fetch_src_categories(game["id"])
    if not categories:
        return results

    current_lower = current_category.lower()
    candidates = []
    for cat in categories:
        cat_name = cat.get("name", "")
        if not cat_name:
            continue
        if cat_name.lower() == current_lower:
            continue
        if cat.get("type") != "per-game":
            continue

        wr_seconds = fetch_category_wr(game["id"], cat["id"])
        if wr_seconds is None:
            continue

        wr_minutes = wr_seconds / 60.0
        delta = wr_minutes - current_estimate_minutes
        if delta <= 0:
            continue
        if delta > max_delta_minutes:
            continue

        candidates.append({
            "name": cat_name,
            "wr_seconds": wr_seconds,
            "wr_minutes": round(wr_minutes, 1),
            "delta_minutes": round(delta, 1),
            "needs_approval": "Yes" if delta >= 15 else "No",
            "category_url": f"{game.get('weblink', '')}/{cat.get('weblink', '')}",
        })

    candidates.sort(key=lambda c: c["delta_minutes"])
    results["upgrades"] = candidates
    return results


def find_incentives(
    game_name: str,
    current_category: str = "",
    current_estimate_minutes: int = 0,
    gdq_bids: list[dict] = None,
) -> dict:
    """Search GDQ tracker and speedrun.com for incentive ideas matching a game.

    Args:
        game_name: Name of the game to search for
        current_category: Current ESA category (e.g. "Any%") — used to
            find category upgrades on speedrun.com
        current_estimate_minutes: Current ESA estimate in minutes — used
            to filter upgrades by time proximity
        gdq_bids: Pre-cached list of GDQ parent bids. If None, fetches
            fresh bids from all 12 GDQ events.
    """
    results = {
        "game": game_name,
        "events_searched": [],
        "incentives": [],
        "src_upgrades": [],
    }

    if gdq_bids is not None:
        results["events_searched"].append({"cached_bids": len(gdq_bids)})
        matches = search_bids_for_game(gdq_bids, game_name)
        seen = set()
        for bid in matches:
            key = (bid["name"], bid["run"])
            if key in seen:
                continue
            seen.add(key)
            results["incentives"].append({
                "name": bid["name"],
                "run": bid["run"],
                "description": bid["description"],
                "category": _categorize_bid(bid),
                "event": bid["event"],
                "confidence": bid.get("confidence", "unknown"),
                "source_url": f"https://tracker.gamesdonequick.com/tracker/bid/{bid['id']}",
            })
    else:
        seen = set()
        for event_name, event_slug in GDQ_EVENTS:
            bids = fetch_event_bids(event_slug)
            results["events_searched"].append({"event": event_name, "slug": event_slug, "bid_count": len(bids)})
            matches = search_bids_for_game(bids, game_name)
            for bid in matches:
                key = (bid["name"], bid["run"])
                if key in seen:
                    continue
                seen.add(key)
                results["incentives"].append({
                    "name": bid["name"],
                    "run": bid["run"],
                    "description": bid["description"],
                    "category": _categorize_bid(bid),
                    "event": bid["event"],
                    "confidence": bid.get("confidence", "unknown"),
                    "source_url": f"https://tracker.gamesdonequick.com/tracker/bid/{bid['id']}",
                })

    if current_category and current_estimate_minutes > 0:
        src = find_category_upgrades(
            game_name,
            current_category=current_category,
            current_estimate_minutes=current_estimate_minutes,
        )
        results["src_game"] = src.get("src_game")
        for upgrade in src.get("upgrades", []):
            results["src_upgrades"].append({
                "name": f"Upgrade to {upgrade['name']}",
                "category": "Target",
                "wr_minutes": upgrade["wr_minutes"],
                "delta_minutes": upgrade["delta_minutes"],
                "needs_approval": upgrade["needs_approval"],
                "source_url": upgrade["category_url"],
            })

        # Fetch subcategory variables for Poll-Bid War suggestions
        src_game = src.get("src_game") or search_src_game(game_name)
        if src_game:
            subcats = fetch_src_subcategories(src_game["id"])
            seen_subcats = set()
            for sc in subcats:
                key = f"{sc['name']}:{','.join(sorted(sc['options']))}"
                if key in seen_subcats:
                    continue
                seen_subcats.add(key)
                results["src_upgrades"].append({
                    "name": f"{sc['name']}: {', '.join(sc['options'][:6])}",
                    "category": "Poll-Bid War",
                    "options": sc["options"],
                    "source": "src_variable",
                    "source_url": f"https://www.speedrun.com/{src_game.get('abbreviation', '')}",
                })

    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.find_incentives <game_name>")
        print("Example: python3 -m src.find_incentives 'Super Mario Bros'")
        sys.exit(1)

    game_name = " ".join(sys.argv[1:])
    results = find_incentives(game_name)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
