"""
API-Football client (api-football.com / RapidAPI v3).

Set API_FOOTBALL_KEY in .env to activate. Without a key this module
raises EnvironmentError — the rest of the app continues from manual data.

Key endpoints used:
    GET /leagues?country=Norway&season=2026      → discover league IDs
    GET /fixtures?league=103&season=2026         → fixtures by league
    GET /standings?league=103&season=2026        → league standings
    GET /teams/statistics?league=X&season=Y&team=Z  → team form + stats
    GET /predictions?fixture=12345               → match predictions

Get a key at: https://rapidapi.com/api-sports/api/api-football
"""
import json
import unicodedata
import urllib.request
import urllib.parse

from config import API_FOOTBALL_KEY

_BASE = "https://v3.football.api-sports.io"

# Known API-Football league IDs for Norwegian domestic + major international
LEAGUE_IDS = {
    "eliteserien":        103,
    "obos-ligaen":        104,
    "nff-cup":            105,
    "toppserien":         725,
    "1-division-women":   915,
    "world-cup":            1,
    "world-cup-women":      6,
    "champions-league":     2,
    "nations-league-a":   954,
}

# NT arrangement_name substring → (api_football_league_id, season, status)
# Checked in order — first match wins.
# IMPORTANT: more specific patterns must come before general ones.
# status: "ok" = covered | "not_covered" = league not in AF | "probe" = may exist, ID unknown
_NT_COMPETITION_MAP: list[tuple[str, int | None, int | None, str]] = [
    # Lower-tier Norwegian domestic — NOT in API-Football
    ("Norsk Tipping-ligaen",            None,   None,   "not_covered"),
    # Norwegian domestic — covered
    ("NOR OBOS-ligaen",                 104,    2026,   "ok"),
    ("OBOS-ligaen",                     104,    2026,   "ok"),
    ("NOR Eliteserien",                 103,    2026,   "ok"),
    ("Eliteserien",                     103,    2026,   "ok"),
    ("NOR Toppserien",                  725,    2026,   "ok"),
    ("Toppserien",                      725,    2026,   "ok"),
    ("NFF Cup",                         105,    2026,   "ok"),
    ("NM Cup",                          105,    2026,   "ok"),
    # International — Women's WC Qualification UEFA
    # AF league 880 "World Cup - Women - Qualification Europe", season=2027
    # (AF uses tournament year as the season label, not the calendar year of the qualifying rounds)
    ("FIFA World Cup, Women, Qualification, UEFA", 880, 2027, "ok"),
    ("FIFA World Cup, Women, Qualification",       880, 2027, "ok"),
    ("World Cup, Women, Qualification",            880, 2027, "ok"),
    # International — Women's WC (tournament itself, MUST come before "FIFA World Cup")
    ("FIFA World Cup, Women",             6,    2027,   "ok"),
    # International — FIFA WC 2026 (Men)
    ("Fotball-VM",                        1,    2026,   "ok"),
    ("FIFA World Cup",                    1,    2026,   "ok"),
    ("World Cup",                         1,    2026,   "ok"),
    # International — Champions League
    ("UEFA Champions League",             2,    2026,   "ok"),
    ("Champions League",                  2,    2026,   "ok"),
    # International — Nations League
    ("UEFA Nations League",               5,    2025,   "ok"),
    ("Nations League",                    5,    2025,   "ok"),
]

# Norwegian team name (lower-cased, pre-normalised) → English (for API-Football matching).
# IMPORTANT: all keys must be in _norm() form (Nordic chars stripped: ø→o, æ→ae, å→a).
# _norm() is applied before the dict lookup in translate_team_name(), so raw Nordic chars
# in keys will never be found.  Use the post-norm ASCII form as the key.
_NO_TO_EN: dict[str, str] = {
    # Scandinavian / European national teams
    "norge": "norway",
    "osterrike": "austria",       # Østerrike → osterrike after _norm()
    "tyskland": "germany",
    "frankrike": "france",
    "nederland": "netherlands",
    "sverige": "sweden",
    "island": "iceland",
    "nord-irland": "northern ireland",
    "tsjekkia": "czech republic",
    "sveits": "switzerland",
    "skottland": "scotland",
    "wales": "wales",
    "england": "england",
    "irland": "ireland",
    "finland": "finland",
    "portugal": "portugal",
    "israel": "israel",
    "serbia": "serbia",
    "danmark": "denmark",
    "slovenia": "slovenia",
    "ukraina": "ukraine",
    "spania": "spain",
    "italia": "italy",
    "belgia": "belgium",
    "kroatia": "croatia",
    "ungarn": "hungary",
    "romania": "romania",
    "slovakia": "slovakia",
    "hellas": "greece",
    "tyrkia": "turkey",
    "turkiye": "turkey",
    "georgia": "georgia",
    "albania": "albania",
    "polen": "poland",            # missing — added
    # Americas
    "brasil": "brazil",
    "marokko": "morocco",
    "elfenbenskysten": "ivory coast",
    "curacao": "curacao",
    "haiti": "haiti",
    "ecuador": "ecuador",
    "usa": "usa",
    # Asia / Oceania
    "australia": "australia",
    "japan": "japan",
    "sor-korea": "south korea",   # Sør-Korea → sor-korea after _norm()
    "saudi-arabia": "saudi arabia",
    "saudi arabia": "saudi arabia",
    # Other
    "qatar": "qatar",
    "tunisia": "tunisia",
    "tunis": "tunisia",
    "cape verde islands": "cape verde islands",
    # AF spelling variants (non-Norwegian, but AF spells differently from common English)
    "ivory coast": "ivory coast",
    "cote d'ivoire": "ivory coast",
    # Norwegian women's clubs (canonical AF spelling, keys in post-norm form)
    "valerenga kvinner": "valerenga w",   # Vålerenga → valerenga after _norm()
    "brann kvinner": "brann w",
    "rosenborg kvinner": "rosenborg w",
    "stabaek kvinner": "stabaek w",       # Stabæk → stabaek after _norm(); value also normalised
    "lsk kvinner": "lsk kvinner w",
    "arna-bjornar": "arna-bjornar",       # Arna-Bjørnar → arna-bjornar after _norm()
    "avaldsnes": "avaldsnes",
}


def _norm(name: str) -> str:
    """
    Lowercase, strip diacritics, replace Nordic precomposed chars, collapse whitespace.
    Handles both standard diacritics (é→e via NFKD) and Nordic chars (ø→o, æ→ae, å→a)
    which do NOT decompose in NFKD and must be replaced explicitly.
    """
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    # Nordic precomposed chars (NFKD-stable, must be mapped manually)
    stripped = (
        stripped
        .replace("ø", "o")   # ø → o
        .replace("æ", "ae")  # æ → ae
        .replace("å", "a")   # å → a
        .replace("ð", "d")   # ð → d  (Icelandic)
        .replace("þ", "th")  # þ → th (Icelandic)
    )
    return " ".join(stripped.split())


def translate_team_name(name: str) -> str:
    """
    Normalize and translate a team name for fuzzy matching.
    Handles both Norwegian→English translation and AF spelling variants
    (e.g. Türkiye→turkey, Ivory Coast→ivory coast).
    Returns the normalized/translated name, or the _norm'd original if not found.
    """
    norm = _norm(name)
    if norm in _NO_TO_EN:
        return _NO_TO_EN[norm]
    # Handle "X Kvinner" / "X K" pattern (Norwegian women's clubs)
    for suffix in (" kvinner", " k"):
        if norm.endswith(suffix):
            base = norm[: -len(suffix)].strip()
            base_en = _NO_TO_EN.get(base, base)
            return f"{base_en} w"
    return norm  # return already-normalized name (not the raw original)


def map_nt_competition(arrangement_name: str) -> tuple[int | None, int | None, str]:
    """
    Map an NT arrangement_name to an API-Football (league_id, season, status).

    Returns (league_id, season, status).
    status: "ok" | "not_covered" | "probe" | "unknown"
    """
    if not arrangement_name:
        return None, None, "unknown"
    arr_lower = arrangement_name.lower()
    for pattern, lid, season, note in _NT_COMPETITION_MAP:
        if pattern.lower() in arr_lower:
            return lid, season, note
    return None, None, "unknown"


def _get(endpoint: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        raise EnvironmentError(
            "API_FOOTBALL_KEY is not set.\n"
            "Add it to .env:\n"
            "  API_FOOTBALL_KEY=your_key_here\n"
            "Get a key at https://rapidapi.com/api-sports/api/api-football"
        )
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_BASE}/{endpoint}?{qs}"
    req = urllib.request.Request(
        url,
        headers={
            "x-rapidapi-key":  API_FOOTBALL_KEY,
            "x-rapidapi-host": "v3.football.api-sports.io",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


# ── Public API ────────────────────────────────────────────────────────────────

def get_leagues(country: str = None, season: int = None) -> list[dict]:
    """Return leagues, optionally filtered by country and/or season."""
    params: dict = {}
    if country:
        params["country"] = country
    if season:
        params["season"] = season
    return _get("leagues", params).get("response", [])


def get_teams(league_id: int, season: int) -> list[dict]:
    """Return teams registered in a league for a season."""
    return _get("teams", {"league": league_id, "season": season}).get("response", [])


def get_standings(league_id: int, season: int) -> list[dict]:
    """
    Return standings for a league/season.
    Returns the raw 'response' list from API-Football.
    """
    return _get("standings", {"league": league_id, "season": season}).get("response", [])


def get_team_statistics(league_id: int, season: int, team_id: int) -> dict | None:
    """
    Return team statistics for a team in a league/season.
    Includes: form string, goals for/against, fixtures played, biggest wins/losses.
    """
    data = _get("teams/statistics", {
        "league": league_id,
        "season": season,
        "team": team_id,
    })
    return data.get("response") or None


def get_fixtures(
    league_id: int = None,
    season: int = None,
    from_date: str = None,
    to_date: str = None,
    date: str = None,
    team_id: int = None,
    fixture_id: int = None,
) -> list[dict]:
    """
    Return fixtures. Supports filtering by league, season, date range, team, or fixture ID.
    Date format: YYYY-MM-DD.
    """
    params: dict = {}
    if fixture_id is not None:
        params["id"] = fixture_id
    if league_id is not None:
        params["league"] = league_id
    if season is not None:
        params["season"] = season
    if date:
        params["date"] = date
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if team_id is not None:
        params["team"] = team_id
    return _get("fixtures", params).get("response", [])


def get_predictions(fixture_id: int) -> dict | None:
    """
    Return AI predictions for an API-Football fixture ID.
    Includes predicted winner, percentage H/D/A, comparison, goals.
    """
    data = _get("predictions", {"fixture": fixture_id})
    resp = data.get("response", [])
    return resp[0] if resp else None


# ── Legacy functions (kept for backwards compatibility) ───────────────────────

def fetch_fixtures_by_league(league_id: int, season: int) -> list[dict]:
    return get_fixtures(league_id=league_id, season=season)


def fetch_fixture(fixture_id: int) -> dict | None:
    results = get_fixtures(fixture_id=fixture_id)
    return results[0] if results else None


def fetch_team(team_id: int) -> dict | None:
    data = _get("teams", {"id": team_id})
    resp = data.get("response", [])
    return resp[0] if resp else None


def fetch_leagues_by_country(country: str) -> list[dict]:
    return get_leagues(country=country)


def ingest_fixtures(league_id: int, season: int, competition_id: str) -> list[str]:
    """
    Pull fixtures from API-Football for a league/season and write them to DB.
    Only fixtures where both teams are already in the registry are ingested.
    Returns list of fixture_ids upserted.

    To add a new team to the registry, edit ingestion/seed.py TEAM_REGISTRY
    and run: python sync.py --seed-only
    """
    from db.coupon import upsert_fixture
    from db.registry import find_team_by_external_id

    raw = fetch_fixtures_by_league(league_id, season)
    fixture_ids = []
    skipped = 0

    for item in raw:
        fix   = item.get("fixture", {})
        teams = item.get("teams", {})

        home_api_id = teams.get("home", {}).get("id")
        away_api_id = teams.get("away", {}).get("id")

        home = find_team_by_external_id(home_api_id) if home_api_id else None
        away = find_team_by_external_id(away_api_id) if away_api_id else None

        if not home or not away:
            skipped += 1
            continue

        fid = upsert_fixture(
            home_team_id=home["team_id"],
            away_team_id=away["team_id"],
            competition_id=competition_id,
            kickoff_utc=fix.get("date", ""),
            external_id=fix.get("id"),
            venue=fix.get("venue", {}).get("name", "") or None,
        )
        fixture_ids.append(fid)

    if skipped:
        print(
            f"  api_football: skipped {skipped} fixtures (teams not in registry). "
            f"Add external_id values to TEAM_REGISTRY and re-run."
        )

    return fixture_ids
