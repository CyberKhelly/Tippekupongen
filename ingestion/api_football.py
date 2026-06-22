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
    # Norwegian 2. Division (AF IDs verified 2026-06-20 via /leagues?country=Norway&season=2026)
    # Group 1 = AF 473, Group 2 = AF 474. Only 2 groups are indexed by AF.
    # NT arrangement_name is "NOR 2.divisjon avd. N" — specific avd must come before catch-all.
    ("2.divisjon avd. 1",          473,  2026,  "ok"),
    ("2.divisjon avd. 2",          474,  2026,  "ok"),
    # Catch-all for 2. Divisjon groups 3–7 (not indexed by AF as of 2026)
    ("2.divisjon",                 None, None,  "not_covered"),
    # Norwegian 3. Division (Norsk Tipping-ligaen avd1-6) — specific entries MUST come before catch-all
    ("Norsk Tipping-ligaen avd1",  774,  2026,  "ok"),
    ("Norsk Tipping-ligaen avd2",  775,  2026,  "ok"),
    ("Norsk Tipping-ligaen avd3",  776,  2026,  "ok"),
    ("Norsk Tipping-ligaen avd4",  777,  2026,  "ok"),
    ("Norsk Tipping-ligaen avd5",  778,  2026,  "ok"),
    ("Norsk Tipping-ligaen avd6",  779,  2026,  "ok"),
    # Catch-all for any other avd not yet explicitly mapped
    ("Norsk Tipping-ligaen",       None, None,  "not_covered"),
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
    "nord irland": "northern ireland",
    "tsjekkia": "czechia",           # AF uses "Czechia" (not "Czech Republic") as of 2026
    "sveits": "switzerland",
    "skottland": "scotland",
    "wales": "wales",
    "england": "england",
    "irland": "ireland",
    "finland": "finland",
    "portugal": "portugal",
    "israel": "israel",
    "irak": "iraq",              # Irak → sor irak after _norm() — AF uses "Iraq"
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
    # Africa
    "sor afrika": "south africa",    # Sør-Afrika → sor afrika after _norm()
    "marokko": "morocco",
    "elfenbenskysten": "ivory coast",
    "dr kongo": "congo dr",          # NT "DR Kongo" — AF spells it "Congo DR" (reversed)
    "senegal": "senegal",
    "ghana": "ghana",
    "algeria": "algeria",
    # Americas
    "brasil": "brazil",
    "kapp verde": "cape verde islands",  # NT "Kapp Verde" — AF: "Cape Verde Islands"
    "curacao": "curacao",
    "haiti": "haiti",
    "ecuador": "ecuador",
    "usa": "usa",
    "panama": "panama",
    "colombia": "colombia",
    "uruguay": "uruguay",
    "paraguay": "paraguay",
    "mexico": "mexico",
    # Asia / Oceania / Middle East
    "australia": "australia",
    "japan": "japan",
    "sor korea": "south korea",    # Sør-Korea → sor korea after _norm()
    "saudi arabia": "saudi arabia",
    "usbekistan": "uzbekistan",    # Usbekistan → usbekistan after _norm()
    "jordan": "jordan",
    "iran": "iran",
    "new zealand": "new zealand",
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
    "arna bjornar": "arna bjornar",        # Arna-Bjørnar → arna bjornar after _norm()
    "avaldsnes": "avaldsnes",
}

# AF name (as returned in fixture/team responses) → correct display name with Norwegian chars.
# Used to normalize opponent_name in recent-match tooltip data.
# Keys: lowercased AF name (may contain English ASCII, without Norwegian chars).
AF_TO_DISPLAY: dict[str, str] = {
    # Norwegian clubs — OBOS/Eliteserien/lower tiers
    "stabaek":            "Stabæk",
    "stabæk":             "Stabæk",
    "stromsgodset":       "Strømsgodset",
    "stroemsgodset":      "Strømsgodset",
    "strommen":           "Strømmen",
    "stroemmen":          "Strømmen",
    "hodd":               "Hødd",
    "aalesund":           "Ålesund",
    "asane":              "Åsane",
    "bodo/glimt":         "Bodø/Glimt",
    "bodo glimt":         "Bodø/Glimt",
    "valerenga":          "Vålerenga",
    "odd ballklubb":      "Odd",
    "odd":                "Odd",
    "ham-kam":            "Ham-Kam",
    "hamkam":             "Ham-Kam",
    "brann":              "Brann",
    "molde":              "Molde",
    "rosenborg":          "Rosenborg",
    "viking":             "Viking",
    "haugesund":          "Haugesund",
    "fredrikstad":        "Fredrikstad",
    "lillestrøm":         "Lillestrøm",
    "lillestrøm sk":      "Lillestrøm",
    "lillestrøm sk":      "Lillestrøm",
    "lillestrom":         "Lillestrøm",
    "lillestrom sk":      "Lillestrøm",
    "kongsvinger":        "Kongsvinger",
    "moss":               "Moss",
    "raufoss":            "Raufoss",
    "bryne":              "Bryne",
    "egersund":           "Egersund",
    "sogndal":            "Sogndal",
    "sandnes ulf":        "Sandnes Ulf",
    "sandnes ulf":        "Sandnes Ulf",
    "ranheim":            "Ranheim",
    "lyn":                "Lyn",
    "grorud":             "Grorud",
    "junkeren":           "Junkeren",
    "start":              "Start",
    "tromsø":             "Tromsø",
    "tromso":             "Tromsø",
    "sarpsborg 08":       "Sarpsborg 08",
    "sarpsborg08":        "Sarpsborg 08",
    "hei":                "HEI",
    "åsane":              "Åsane",
    # Norwegian women's clubs
    "valerenga w":        "Vålerenga Kvinner",
    "brann w":            "Brann Kvinner",
    "rosenborg w":        "Rosenborg Kvinner",
    "stabaek w":          "Stabæk Kvinner",
    "arna bjornar":       "Arna-Bjørnar",
    "avaldsnes":          "Avaldsnes",
    # Common AF casing/spelling fixes for non-Norwegian teams
    "cape verde islands": "Kapp Verde",
    "congo dr":           "DR Kongo",
    "ivory coast":        "Elfenbenskysten",
    "south korea":        "Sør-Korea",
    "south africa":       "Sør-Afrika",
}


def normalize_opponent_name(name: str | None) -> str | None:
    """
    Normalize an API-Football opponent name to the correct display name with
    Norwegian characters.  Returns the input unchanged if no mapping is found.
    """
    if not name:
        return name
    key = name.strip().lower()
    return AF_TO_DISPLAY.get(key, name)


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
        .replace("-", " ")   # hyphen → space (Ørn-Horten == Ørn Horten)
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
    qs = urllib.parse.urlencode(params)
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
    last: int = None,
) -> list[dict]:
    """
    Return fixtures. Supports filtering by league, season, date range, team, or fixture ID.
    Date format: YYYY-MM-DD.
    Use last=5 with team_id to get the last N completed fixtures for a team.
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
    if last is not None:
        params["last"] = last
    return _get("fixtures", params).get("response", [])


def get_fixture_statistics(fixture_id: int) -> list[dict]:
    """
    Return per-team statistics for a completed fixture.
    Returns a list of 2 dicts (one per team):
      {'team': {'id': int, 'name': str}, 'statistics': [{'type': str, 'value': ...}]}
    Returns [] when the fixture has no stats (some leagues not covered on Pro plan).
    """
    return _get("fixtures/statistics", {"fixture": fixture_id}).get("response", [])


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
