"""
The Odds API client (theoddsapi.com).

Fetches H2H (1X2) odds aggregated from 40+ bookmakers.
Pinnacle odds are preferred as the sharpest market signal; other sharp/liquid
bookmakers are used as fallback when Pinnacle has no line for a fixture.

Set ODDS_API_KEY in .env to activate.
Free tier: 500 requests/month.
Get a key at: https://the-odds-api.com

Sport keys (soccer examples):
    soccer_epl             → English Premier League
    soccer_uefa_champs_league
    soccer_norway_eliteserien
    soccer_fifa_world_cup

Run `python -c "from ingestion.odds_api import list_sports; list_sports()"` to
see all available sport keys on your subscription.
"""
import json
import unicodedata
import urllib.request

from config import ODDS_API_KEY

_BASE = "https://api.the-odds-api.com/v4"

# Bookmakers tried in order when building the best available line.
# Pinnacle is the sharpest; the rest are well-known European/Nordic books.
_BOOKMAKER_PRIORITY = [
    "pinnacle",
    "betsson",
    "unibet_se",
    "unibet_nl",
    "unibet_uk",
    "unibet_fr",
    "leovegas",
    "leovegas_se",
    "marathonbet",
    "betfair_ex_eu",
    "betfair_ex_uk",
    "nordicbet",
    "coolbet",
    "casumo",
    "coral",
    "williamhill",
    "paddypower",
    "skybet",
]


def _get(path: str, params: dict | None = None) -> list | dict:
    if not ODDS_API_KEY:
        raise EnvironmentError(
            "ODDS_API_KEY is not set.\n"
            "Add it to .env:\n"
            "  ODDS_API_KEY=your_key_here\n"
            "Get a free key at https://the-odds-api.com"
        )
    params = params or {}
    params["apiKey"] = ODDS_API_KEY
    qs  = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_BASE}/{path}?{qs}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def list_sports() -> list[dict]:
    """Return all available sports on your subscription."""
    return _get("sports", {"all": "true"})


def fetch_odds(
    sport_key: str,
    regions: str = "eu,uk",
    markets: str = "h2h",
    bookmakers: str | None = None,
) -> list[dict]:
    """
    Fetch H2H odds for all upcoming events in a sport.

    bookmakers: comma-separated list to filter (e.g. "pinnacle").
                Pass None (default) to return all available bookmakers —
                needed for the multi-bookmaker fallback logic.

    Returns list of event objects, each containing a `bookmakers` list.
    """
    params: dict = {"regions": regions, "markets": markets}
    if bookmakers:
        params["bookmakers"] = bookmakers
    return _get(f"sports/{sport_key}/odds", params)


def extract_h2h(
    event: dict, bookmaker_key: str = "pinnacle"
) -> tuple[float, float, float] | None:
    """
    Pull (odds_h, odds_u, odds_b) from an event for a specific bookmaker.
    Returns None if the bookmaker or market isn't present.
    """
    home = event.get("home_team", "")
    away = event.get("away_team", "")

    for bm in event.get("bookmakers", []):
        if bm["key"] != bookmaker_key:
            continue
        for market in bm.get("markets", []):
            if market["key"] != "h2h":
                continue
            by_name = {o["name"]: o["price"] for o in market["outcomes"]}
            h = by_name.get(home)
            b = by_name.get(away)
            u = by_name.get("Draw")
            if h and u and b:
                return (float(h), float(u), float(b))

    return None


def extract_h2h_best(
    event: dict,
) -> tuple[float, float, float, str] | None:
    """
    Pull the best available H2H line from an event, trying bookmakers in
    _BOOKMAKER_PRIORITY order.

    Returns (odds_h, odds_u, odds_b, bookmaker_key), or None if no line found.
    """
    home = event.get("home_team", "")
    away = event.get("away_team", "")

    available: dict[str, tuple[float, float, float]] = {}
    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            if market["key"] != "h2h":
                continue
            by_name = {o["name"]: o["price"] for o in market["outcomes"]}
            h = by_name.get(home)
            b = by_name.get(away)
            u = by_name.get("Draw")
            if h and u and b:
                available[bm["key"]] = (float(h), float(u), float(b))

    for bkm in _BOOKMAKER_PRIORITY:
        if bkm in available:
            return (*available[bkm], bkm)

    # Any remaining bookmaker not in the priority list
    for bkm, odds in available.items():
        return (*odds, bkm)

    return None


def _ascii(s: str) -> str:
    """Strip diacritics so 'Curaçao' matches 'Curacao', 'Côte d'Ivoire' matches, etc."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def _name_matches(canonical: str, api_name: str) -> bool:
    """Fuzzy match: canonical team name against The Odds API event team name."""
    c = _ascii(canonical.lower().strip())
    a = _ascii(api_name.lower().strip())
    return c in a or a in c or c[:6] == a[:6]


def ingest_odds_for_coupon(
    coupon_id: str,
    sport_keys: list[str] | None = None,
    write_snapshot: bool = True,
) -> int:
    """
    Match coupon fixtures to The Odds API events by team name, then store
    the best available bookmaker odds in the DB.

    Priority: Pinnacle > betsson > unibet_se > leovegas > ... (see _BOOKMAKER_PRIORITY).
    All bookmakers are fetched in one API call per sport key — no extra requests.

    Returns number of fixtures matched.

    sport_keys: list of The Odds API sport keys to search.
                Defaults to a broad set covering international football.
    write_snapshot: if True (default), also write a timestamped entry to
                    odds_snapshots for CLV and movement tracking.
    """
    from db.coupon import get_coupon_matches, upsert_odds
    from db.registry import get_team
    from db.odds_movement import save_snapshot

    if sport_keys is None:
        sport_keys = [
            "soccer_fifa_world_cup",
            "soccer_norway_eliteserien",
            "soccer_uefa_nations_league",
            "soccer_uefa_champs_league",
            "soccer_epl",
            "soccer_germany_bundesliga",
            "soccer_france_ligue_one",
            "soccer_spain_la_liga",
            "soccer_italy_serie_a",
            "soccer_portugal_primeira_liga",
            "soccer_turkey_super_league",
            "soccer_spl",
            "soccer_netherlands_eredivisie",
            "soccer_denmark_superliga",
            "soccer_sweden_allsvenskan",
        ]

    rows      = get_coupon_matches(coupon_id)
    matched   = set()
    total_new = 0

    for sport_key in sport_keys:
        try:
            # Fetch all bookmakers in one call — the priority logic in
            # extract_h2h_best() picks the sharpest available line.
            events = fetch_odds(sport_key)
        except Exception as exc:
            print(f"  odds_api: {sport_key} -- {exc}")
            continue

        for event in events:
            for row in rows:
                if row["fixture_id"] in matched:
                    continue
                home = get_team(row["home_team_id"])
                away = get_team(row["away_team_id"])
                if not home or not away:
                    continue
                if (
                    _name_matches(home["name_canonical"], event.get("home_team", ""))
                    and _name_matches(away["name_canonical"], event.get("away_team", ""))
                ):
                    best = extract_h2h_best(event)
                    if best:
                        oh, ou, ob, bkm = best
                        upsert_odds(row["fixture_id"], bkm, oh, ou, ob)
                        if write_snapshot:
                            save_snapshot(
                                fixture_id=row["fixture_id"],
                                bookmaker=bkm,
                                market="h2h",
                                odds_h=oh, odds_u=ou, odds_b=ob,
                                source="the_odds_api",
                            )
                        matched.add(row["fixture_id"])
                        total_new += 1

    return total_new
