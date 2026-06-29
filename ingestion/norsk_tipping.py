"""
Norsk Tipping fixture ingestion client.

Endpoint: GET https://api.norsk-tipping.no/Content/v1/api/pages/sport/tipping/spill

Returns gameDays with MIDWEEK / SATURDAY / SUNDAY coupon types, including:
  - match IDs, BetRadar IDs, kickoff times, arrangement names
  - expert tip percentages and public/people tip percentages

NOTE: Expert/people tip percentages are stored separately from bookmaker odds.
      They are crowd-sentiment signals, not probability estimates.
      Do not use them as the probability baseline.
"""
import hashlib
import json
import re
import unicodedata
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Primary endpoint (PoolGamesSportInfo — current as of 2026-06)
_NT_API_URL  = "https://api.norsk-tipping.no/PoolGamesSportInfo/v1/api/tipping/live-info"
# Legacy endpoint kept as fallback (returned 204 in 2026-06, may be reactivated)
_NT_API_URL_LEGACY = "https://api.norsk-tipping.no/Content/v1/api/pages/sport/tipping/spill"
_NT_HTML_URL = "https://www.norsk-tipping.no/sport/tipping"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json, text/html, */*",
    "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
}

_DAY_TYPE_TO_KEY = {
    "MIDWEEK":  "midtuke",
    "SATURDAY": "lordag",
    "SUNDAY":   "sondag",
}

_DAY_TYPE_TO_LABEL = {
    "midtuke": "Midtuke",
    "lordag":  "Lørdag",
    "sondag":  "Søndag",
}


# ── Low-level fetch ──────────────────────────────────────────────────────────────

def _fetch_json(url: str) -> dict | list | None:
    req = urllib.request.Request(url, headers={
        **_HEADERS,
        "Referer": "https://www.norsk-tipping.no/",
        "Origin":  "https://www.norsk-tipping.no",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ct  = resp.headers.get("Content-Type", "")
            raw = resp.read()
            if not raw:
                print(f"  nt: API returned HTTP {resp.status} (no content) — "
                      "coupons may not be published yet for this week.")
                return None
            if "json" not in ct and raw[:1] not in (b"{", b"["):
                print(f"  nt: API returned non-JSON content (CT: {ct!r}, "
                      f"first bytes: {raw[:40]!r})")
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        print(f"  nt: HTTP {exc.code} from {url}")
        return None
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"  nt: fetch error — {exc}")
        return None


def _fetch_html(url: str) -> str | None:
    req = urllib.request.Request(url, headers={
        **_HEADERS, "Accept": "text/html,application/xhtml+xml,*/*"
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            charset = "utf-8"
            ct = resp.headers.get("Content-Type", "")
            if "charset=" in ct:
                charset = ct.split("charset=")[-1].strip().split(";")[0]
            return resp.read().decode(charset, errors="replace")
    except Exception as exc:
        print(f"  nt: HTML fetch error — {exc}")
        return None


# ── Field extraction helpers ─────────────────────────────────────────────────────

def _pick(d: dict, *keys, default=None):
    """Return the first value found among the given key names."""
    for k in keys:
        if k in d:
            return d[k]
    return default


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return round(f, 4)
    except (TypeError, ValueError):
        return None


def _normalize_name(name: str) -> str:
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    ascii_only = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(ascii_only.split())


def _slugify(name: str, gender: str, age_group: str) -> str:
    """Generate a team_id slug from a display name + identity fields."""
    nfkd = unicodedata.normalize("NFKD", name.lower())
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    ascii_name = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")
    g = "m" if gender == "men" else "w"
    return f"{ascii_name}-{g}-{age_group}"


# Mapping from NT Norwegian national-team names to English canonical names used by
# The Odds API (Pinnacle). Add entries here whenever a new NT Norwegian name doesn't
# match the English name used by the odds provider.
_NO_TO_EN: dict[str, str] = {
    "Elfenbenskysten": "Ivory Coast",
    "Tyskland":        "Germany",
    "Frankrike":       "France",
    "Spania":          "Spain",
    "Nederland":       "Netherlands",
    "Sverige":         "Sweden",
    "Sveits":          "Switzerland",
    "Østerrike":       "Austria",
    "Tsjekkia":        "Czech Republic",
    "Tyrkia":          "Turkey",
    "Skottland":       "Scotland",
    "Marokko":         "Morocco",
    "Brasil":          "Brazil",
    "Belgia":          "Belgium",
    "Ungarn":          "Hungary",
    "Polen":           "Poland",
    "Ukraina":         "Ukraine",
    "Russland":        "Russia",
    "Italia":          "Italy",
    "Irland":          "Ireland",
    "Island":          "Iceland",
    "Nord-Irland":     "Northern Ireland",
    "Hellas":          "Greece",
    "Kroatia":         "Croatia",
    "Romania":         "Romania",
    "Hviterussland":   "Belarus",
    "Nord-Makedonia":  "North Macedonia",
    "Aserbajdsjan":    "Azerbaijan",
    "Georgia":         "Georgia",
    "Kasakhstan":      "Kazakhstan",
    "Moldova":         "Moldova",
    "Kosovo":          "Kosovo",
    "Kina":            "China",
    "Sør-Korea":       "South Korea",
    "Australia":       "Australia",
    "Japan":           "Japan",
    "USA":             "United States",
    "Canada":          "Canada",
    "Mexico":          "Mexico",
    "Argentina":       "Argentina",
    "Colombia":        "Colombia",
    "Chile":           "Chile",
    "Uruguay":         "Uruguay",
    "Ecuador":         "Ecuador",
    "Venezuela":       "Venezuela",
    "Bolivia":         "Bolivia",
    "Paraguay":        "Paraguay",
    "Peru":            "Peru",
    "Tunisia":         "Tunisia",
    "Nigeria":         "Nigeria",
    "Ghana":           "Ghana",
    "Kamerun":         "Cameroon",
    "Senegal":         "Senegal",
    "Algerie":         "Algeria",
    "Egypt":           "Egypt",
    "Curacao":         "Curaçao",
}


def _canonical_name(name_local: str, country_iso: str) -> str:
    """
    Return the English canonical name for a team.
    For national teams (country_iso == 'INT'), apply the Norwegian→English mapping.
    For club teams, the Norwegian local name is already the canonical name.
    """
    if country_iso == "INT":
        return _NO_TO_EN.get(name_local, name_local)
    return name_local


def _infer_gender_age(arrangement_name: str) -> tuple[str, str]:
    """
    Infer (gender, age_group) from NT's arrangement/competition name.
    Called ONCE when a new team is created; the result is stored permanently.
    """
    name = (arrangement_name or "").lower()
    # Age group — check before gender ("U21 kvinner" → women/u21)
    if "u21" in name:
        return ("men", "u21")
    if "u19" in name:
        return ("men", "u19")
    if "u17" in name:
        return ("men", "u17")
    # Gender
    if any(w in name for w in ("kvinner", "women", "damer", "feminine", "ladies")):
        return ("women", "senior")
    return ("men", "senior")


# ── Team auto-resolution ─────────────────────────────────────────────────────────

def _resolve_or_create_team(
    nt_team_id: str,
    betradar_id: int | None,
    name_local: str,
    arrangement_name: str,
    country_iso: str,
) -> str:
    """
    Resolve an NT team to our team_id slug.

    Look-up order:
      1. By nt_team_id (exact — fastest path after first encounter)
      2. By alias (normalized name match — links existing registry entries)
      3. Create a new team (new team, infer gender/age from arrangement_name)

    Returns the team_id slug.
    """
    from db.registry import (
        find_team_by_nt_id, find_team_by_alias,
        upsert_team, upsert_alias, get_team,
    )
    from db.coupon import log_coupon_event

    # 1. Known NT team ID
    existing = find_team_by_nt_id(nt_team_id)
    if existing:
        # Back-fill betradar_id if we now have it and didn't before
        if betradar_id and not existing.get("betradar_id"):
            upsert_team(
                team_id=existing["team_id"],
                name_canonical=existing["name_canonical"],
                gender=existing["gender"],
                age_group=existing["age_group"],
                team_type=existing["team_type"],
                country_iso=existing["country_iso"],
                name_local=existing.get("name_local", ""),
                nt_team_id=nt_team_id,
                betradar_id=betradar_id,
            )
        return existing["team_id"]

    # 2. Known by alias (matches existing week-23 registry entries)
    existing = find_team_by_alias(name_local)
    if existing:
        # Link the NT team ID to this existing team
        upsert_team(
            team_id=existing["team_id"],
            name_canonical=existing["name_canonical"],
            gender=existing["gender"],
            age_group=existing["age_group"],
            team_type=existing["team_type"],
            country_iso=existing["country_iso"],
            name_local=name_local,
            nt_team_id=nt_team_id,
            betradar_id=betradar_id,
        )
        return existing["team_id"]

    # 3. New team — infer gender/age from arrangement_name, create, log for review
    gender, age_group = _infer_gender_age(arrangement_name)
    team_type = "national" if len(country_iso) <= 3 else "club"
    team_id = _slugify(name_local, gender, age_group)

    # Avoid slug collisions — append nt_team_id suffix if slug already used
    existing_by_slug = get_team(team_id)
    if existing_by_slug and existing_by_slug.get("nt_team_id") != nt_team_id:
        team_id = f"{team_id}-{nt_team_id}"

    name_en = _canonical_name(name_local, country_iso)
    upsert_team(
        team_id=team_id,
        name_canonical=name_en,  # English name for odds-source matching
        gender=gender,
        age_group=age_group,
        team_type=team_type,
        country_iso=country_iso,
        name_local=name_local,
        nt_team_id=nt_team_id,
        betradar_id=betradar_id,
    )
    upsert_alias(team_id, name_local, "nt")

    # Log for review when arrangement is ambiguous ("Vennekamp", "Privatlandskamp", etc.)
    ambiguous_arrangements = {"vennekamp", "privatlandskamp", "treningskamp", "friendly"}
    if _normalize_name(arrangement_name or "") in ambiguous_arrangements or not arrangement_name:
        log_coupon_event(
            coupon_id="__team_review__",
            event="new_team_needs_review",
            detail={
                "team_id": team_id,
                "nt_team_id": nt_team_id,
                "name_local": name_local,
                "arrangement_name": arrangement_name,
                "inferred_gender": gender,
                "inferred_age_group": age_group,
            },
        )
        print(
            f"  nt: NEW TEAM needs review — {name_local!r} "
            f"(arrangement: {arrangement_name!r}, inferred: {gender}/{age_group}). "
            f"Run: python sync.py --review"
        )
    else:
        print(f"  nt: new team auto-created — {team_id} ({name_local}, {gender}/{age_group})")

    return team_id


# ── Content hash ─────────────────────────────────────────────────────────────────

def _content_hash(matches: list[dict]) -> str:
    """SHA256 of stable fixture identifiers for change detection."""
    payload = sorted(
        (m.get("nt_match_id", ""), m.get("home_nt_team_id", ""),
         m.get("away_nt_team_id", ""), m.get("kickoff_utc", ""))
        for m in matches
    )
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


# ── Country ISO heuristic for new API (no country code in response) ──────────────

def _infer_country_iso(arrangement_name: str) -> str:
    """
    Heuristic to derive a country_iso placeholder from arrangement name.
    Returns "INT" (len ≤ 3 → team_type="national") for international
    tournaments, "CLUB" (len > 3 → team_type="club") for domestic leagues.
    """
    name = (arrangement_name or "").lower()
    national_kws = (
        "world cup", "fotball-vm", "nations league", "qualification",
        "fifa", "uefa euro", "conmebol", "concacaf", "olympic",
        " vm,", "vm ", "wc ",
    )
    if any(kw in name for kw in national_kws):
        return "INT"
    return "CLUB"


# ── New-format parser (PoolGamesSportInfo tipping/live-info) ─────────────────────

def parse_live_info_response(data: dict) -> list[dict]:
    """
    Parse the PoolGamesSportInfo /tipping/live-info response (2026 format).

    New structure:
      {
        "gameDays": [
          {
            "dayType": "MIDWEEK" | "SATURDAY" | "SUNDAY",
            "game": {
              "gameEngineBetObjectId": int,       ← nt_game_day_id
              "matches": [
                {
                  "gameEngineEventId": int,         ← nt_match_id
                  "gameEngineSortingNumber": int,   ← match_number
                  "gameEngineBetRadarId": int,      ← betradar_match_id
                  "date": str,                      ← kickoff_utc
                  "arrangement": {"name": str},
                  "teams": {
                    "home": {"id": int, "webName": str},
                    "away": {"id": int, "webName": str},
                  }
                },
                ...
              ],
              "tips": {
                "fullTime": {
                  "expert":  [{home, draw, away}, ...],  ← indexed by match pos
                  "peoples": [{home, draw, away}, ...],
                }
              },
              "sales": {
                "fullTime": {"saleStopDate": str}       ← deadline
              }
            }
          },
          ...
        ]
      }
    """
    game_days = data.get("gameDays", [])
    if not game_days:
        return []

    result = []
    for gd in game_days:
        if not isinstance(gd, dict):
            continue

        day_type = str(gd.get("dayType", "")).upper()
        key = _DAY_TYPE_TO_KEY.get(day_type)
        if not key:
            continue

        game = gd.get("game")
        if not isinstance(game, dict):
            continue

        nt_game_day_id = str(game.get("gameEngineBetObjectId", ""))
        ft_sales = game.get("sales", {}).get("fullTime", {})
        deadline = ft_sales.get("saleStopDate", "")
        omsetning_raw = ft_sales.get("saleAmount", {}).get("amount")
        omsetning = float(omsetning_raw) if omsetning_raw else None

        tips_ft = game.get("tips", {}).get("fullTime", {})
        expert_tips  = tips_ft.get("expert",  [])
        peoples_tips = tips_ft.get("peoples", [])

        raw_matches = game.get("matches", [])
        if not isinstance(raw_matches, list):
            continue

        parsed_matches = []
        for i, m in enumerate(raw_matches):
            if not isinstance(m, dict):
                continue

            nt_match_id = str(m.get("gameEngineEventId", ""))
            if not nt_match_id:
                continue

            sort_num         = m.get("gameEngineSortingNumber", i + 1)
            betradar_match_id = m.get("gameEngineBetRadarId")
            kickoff_utc      = m.get("date", "")
            arrangement_name = m.get("arrangement", {}).get("name", "")

            home_raw = m.get("teams", {}).get("home", {})
            away_raw = m.get("teams", {}).get("away", {})
            home_name      = str(home_raw.get("webName", ""))
            away_name      = str(away_raw.get("webName", ""))
            home_nt_team_id = str(home_raw.get("id", ""))
            away_nt_team_id = str(away_raw.get("id", ""))

            if not home_name or not away_name or not home_nt_team_id:
                continue

            country_iso = _infer_country_iso(arrangement_name)

            tip_e = expert_tips[i]  if i < len(expert_tips)  else {}
            tip_p = peoples_tips[i] if i < len(peoples_tips) else {}

            def _pct(d: dict, key_: str) -> float | None:
                v = d.get(key_)
                return float(v) if v is not None else None

            parsed_matches.append({
                "match_number":      sort_num,
                "nt_match_id":       nt_match_id,
                "betradar_match_id": betradar_match_id,
                "kickoff_utc":       kickoff_utc,
                "arrangement_name":  arrangement_name,
                "home_nt_team_id":   home_nt_team_id,
                "home_betradar_id":  None,
                "home_name":         home_name,
                "home_country_iso":  country_iso,
                "away_nt_team_id":   away_nt_team_id,
                "away_betradar_id":  None,
                "away_name":         away_name,
                "away_country_iso":  country_iso,
                "expert_h": _pct(tip_e, "home"),
                "expert_u": _pct(tip_e, "draw"),
                "expert_b": _pct(tip_e, "away"),
                "public_h": _pct(tip_p, "home"),
                "public_u": _pct(tip_p, "draw"),
                "public_b": _pct(tip_p, "away"),
            })

        if not parsed_matches:
            continue

        result.append({
            "key":            key,
            "day_type":       day_type,
            "nt_game_day_id": nt_game_day_id,
            "label":          _DAY_TYPE_TO_LABEL.get(key, key.capitalize()),
            "deadline":       deadline,
            "omsetning":      omsetning,
            "matches":        parsed_matches,
        })

    return result


# ── Old-format parser (Content API / __NEXT_DATA__) ──────────────────────────────

def _parse_team(raw: dict, arrangement_name: str) -> dict:
    """
    Extract team identity fields from an NT team object.
    Field names are tried in order of likelihood based on NT's API convention.
    """
    nt_team_id = str(
        _pick(raw, "id", "teamId", "team_id", "ntTeamId", default="")
    )
    betradar_id_raw = _pick(raw, "betRadarId", "betradarmatchid", "betradar_id",
                             "betradarId", "betRadarTeamId", "betradariD")
    betradar_id = int(betradar_id_raw) if betradar_id_raw else None

    name = str(_pick(raw, "name", "teamName", "displayName", default=""))
    country_iso = str(_pick(raw, "countryCode", "country_code", "isoCode",
                             "country", default="XX"))[:5]

    return {
        "nt_team_id":  nt_team_id,
        "betradar_id": betradar_id,
        "name":        name,
        "country_iso": country_iso,
    }


def _parse_tips(raw: dict, prefix: str) -> tuple[float | None, float | None, float | None]:
    """
    Extract H/U/B tip percentages from an object, trying common key patterns.
    Returns (pct_h, pct_u, pct_b) or (None, None, None) if not found.
    """
    # Try object with sub-keys first: {"home": 45.5, "draw": 30.2, "away": 24.3}
    sub = _pick(raw, prefix, prefix.lower(), prefix.upper())
    if isinstance(sub, dict):
        h = _safe_float(_pick(sub, "home", "H", "hjemme", "1"))
        u = _safe_float(_pick(sub, "draw", "U", "uavgjort", "X", "tie"))
        b = _safe_float(_pick(sub, "away", "B", "borte", "2"))
        if h is not None:
            return h, u, b

    # Try flat keys: expertHome, expertDraw, expertAway
    h = _safe_float(_pick(raw, f"{prefix}Home", f"{prefix}H", f"{prefix}_home"))
    u = _safe_float(_pick(raw, f"{prefix}Draw", f"{prefix}U", f"{prefix}_draw"))
    b = _safe_float(_pick(raw, f"{prefix}Away", f"{prefix}B", f"{prefix}_away"))
    if h is not None:
        return h, u, b

    return None, None, None


def _parse_match(raw: dict, match_number: int) -> dict | None:
    """
    Parse one match from the NT game day response.
    Returns a structured dict or None if essential fields are missing.
    """
    nt_match_id = str(_pick(raw, "id", "matchId", "match_id", "ntMatchId", default=""))
    if not nt_match_id:
        return None

    betradar_raw = _pick(raw, "betRadarId", "betRadarMatchId", "betradarId",
                          "betradar_id", "betradarmatchid", "betradarMatchId")
    betradar_match_id = int(betradar_raw) if betradar_raw else None

    # Kickoff — try common names; convert to UTC ISO string
    kickoff_raw = _pick(raw, "kickoff", "startTime", "matchTime", "kickoffTime",
                         "start", "date", "scheduledAt")
    kickoff_utc = str(kickoff_raw) if kickoff_raw else ""

    arrangement_name = str(
        _pick(raw, "arrangement", "arrangementName", "competition",
               "competitionName", "league", "tournamentName", default="")
    )

    # Teams — field names vary; try both "home"/"away" objects and "homeTeam"/"awayTeam"
    home_raw = _pick(raw, "homeTeam", "home_team", "home")
    away_raw = _pick(raw, "awayTeam", "away_team", "away")
    if not isinstance(home_raw, dict) or not isinstance(away_raw, dict):
        return None

    home = _parse_team(home_raw, arrangement_name)
    away = _parse_team(away_raw, arrangement_name)
    if not home["nt_team_id"] or not away["nt_team_id"]:
        return None

    # Tips percentages — expert tips and people/public tips
    expert_h, expert_u, expert_b = _parse_tips(raw, "expert")
    if expert_h is None:
        expert_h, expert_u, expert_b = _parse_tips(raw, "expertTips")

    public_h, public_u, public_b = _parse_tips(raw, "public")
    if public_h is None:
        public_h, public_u, public_b = _parse_tips(raw, "peopleTips")
    if public_h is None:
        public_h, public_u, public_b = _parse_tips(raw, "people")

    return {
        "match_number":      match_number,
        "nt_match_id":       nt_match_id,
        "betradar_match_id": betradar_match_id,
        "kickoff_utc":       kickoff_utc,
        "arrangement_name":  arrangement_name,
        "home_nt_team_id":   home["nt_team_id"],
        "home_betradar_id":  home["betradar_id"],
        "home_name":         home["name"],
        "home_country_iso":  home["country_iso"],
        "away_nt_team_id":   away["nt_team_id"],
        "away_betradar_id":  away["betradar_id"],
        "away_name":         away["name"],
        "away_country_iso":  away["country_iso"],
        # Tips — crowd/expert sentiment only; NOT bookmaker odds
        "expert_h":          expert_h,
        "expert_u":          expert_u,
        "expert_b":          expert_b,
        "public_h":          public_h,
        "public_u":          public_u,
        "public_b":          public_b,
    }


def _find_game_days(data) -> list:
    """
    Navigate the API response to find the gameDays list.
    Handles both flat {"gameDays": [...]} and nested page-content structures.
    """
    if isinstance(data, list):
        return data  # top-level list of game days

    if isinstance(data, dict):
        # Direct gameDays key
        gd = _pick(data, "gameDays", "game_days", "gamedays", "rounds", "coupons")
        if isinstance(gd, list):
            return gd

        # Nested under content/data wrappers (page content API pattern)
        for wrapper_key in ("data", "content", "pageData", "props", "result"):
            wrapped = data.get(wrapper_key)
            if isinstance(wrapped, dict):
                gd = _pick(wrapped, "gameDays", "game_days", "rounds", "coupons",
                            "gamedays", "tipping")
                if isinstance(gd, list):
                    return gd

        # Deep Next.js: data["props"]["pageProps"]["..."]
        props = data.get("props", {})
        if isinstance(props, dict):
            page_props = props.get("pageProps", {})
            if isinstance(page_props, dict):
                for key, val in page_props.items():
                    if isinstance(val, list) and val and isinstance(val[0], dict):
                        gd = _pick(val[0], "gameDays", "game_days", "matches")
                        if isinstance(gd, list):
                            return gd
                        return val  # the list itself might be game days

    return []


def parse_game_days(raw: dict | list) -> list[dict]:
    """
    Parse the NT API response into a list of coupon dicts, one per dayType.

    Returns:
        [
          {
            "key":            "midtuke" | "lordag" | "sondag",
            "day_type":       "MIDWEEK" | "SATURDAY" | "SUNDAY",
            "nt_game_day_id": str,
            "label":          str,
            "deadline":       str (ISO 8601),
            "matches":        [{ ... parsed match dict ... }, ...]
          },
          ...
        ]
    """
    game_days = _find_game_days(raw)
    if not game_days:
        print("  nt: could not locate gameDays in response — check field names.")
        print("  nt: run with --nt-debug to print the raw response structure.")
        return []

    result = []
    for gd in game_days:
        if not isinstance(gd, dict):
            continue

        day_type = str(_pick(gd, "dayType", "day_type", "type", "couponType", default="")).upper()
        key = _DAY_TYPE_TO_KEY.get(day_type)
        if not key:
            continue  # skip unknown day types

        nt_game_day_id = str(_pick(gd, "id", "gameDayId", "game_day_id", default=""))
        deadline_raw   = _pick(gd, "deadline", "cutoffTime", "cutoff", "closingTime",
                                "registrationDeadline", "endTime")
        deadline       = str(deadline_raw) if deadline_raw else ""
        label_raw      = _pick(gd, "label", "name", "title")
        label = str(label_raw) if label_raw else _DAY_TYPE_TO_LABEL.get(key, key.capitalize())

        raw_matches = _pick(gd, "matches", "events", "games", "fixtures", default=[])
        if not isinstance(raw_matches, list):
            continue

        parsed_matches = []
        for i, m in enumerate(raw_matches, 1):
            if not isinstance(m, dict):
                continue
            pm = _parse_match(m, i)
            if pm:
                parsed_matches.append(pm)

        if not parsed_matches:
            continue

        result.append({
            "key":            key,
            "day_type":       day_type,
            "nt_game_day_id": nt_game_day_id,
            "label":          label,
            "deadline":       deadline,
            "matches":        parsed_matches,
        })

    return result


# ── Public entry points ──────────────────────────────────────────────────────────

def fetch_game_days(debug: bool = False) -> list[dict]:
    """
    Fetch and parse the current NT coupon data.

    Attempt order:
      1. PoolGamesSportInfo /tipping/live-info  (primary, new 2026 format)
      2. Content API /pages/sport/tipping/spill  (legacy, pre-2026 format)
      3. HTML scrape of NT website               (last resort)

    Returns parsed coupon list (empty on total failure).
    """
    # Method 1: new primary endpoint (PoolGamesSportInfo)
    raw = _fetch_json(_NT_API_URL)
    if raw is not None:
        if debug:
            print(json.dumps(raw, indent=2, ensure_ascii=False)[:3000])
        result = parse_live_info_response(raw)
        if result:
            return result
        print("  nt: new API returned data but parser found no gameDays — trying legacy endpoint.")

    # Method 2: legacy Content API
    print("  nt: trying legacy Content API...")
    raw_legacy = _fetch_json(_NT_API_URL_LEGACY)
    if raw_legacy is not None:
        if debug:
            print(json.dumps(raw_legacy, indent=2, ensure_ascii=False)[:3000])
        result = parse_game_days(raw_legacy)
        if result:
            return result
        print("  nt: legacy API returned data but parser found no gameDays.")

    # Method 3: HTML scrape (NT website may not embed __NEXT_DATA__ in newer versions)
    print("  nt: falling back to HTML scrape...")
    html = _fetch_html(_NT_HTML_URL)
    if html:
        m = re.search(
            r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if m:
            try:
                next_data = json.loads(m.group(1))
                if debug:
                    print(json.dumps(next_data, indent=2, ensure_ascii=False)[:3000])
                result = parse_game_days(next_data)
                if result:
                    return result
            except json.JSONDecodeError:
                pass
        print("  nt: HTML scrape did not yield usable coupon data.")

    print("  nt: all fetch methods failed — using flat-file fallback.")
    return []


def ingest_game_days(week: int, year: int, debug: bool = False,
                     force_refresh: bool = False) -> bool:
    """
    Full pipeline: fetch NT data → resolve teams → write coupons/fixtures/tips to DB.

    When force_refresh=True the content-hash check is skipped and coupon_fixtures
    are cleared before re-insertion, so stale/removed fixtures do not accumulate.
    Historical coupon_predictions are never touched.

    Returns True if at least one coupon was ingested successfully.
    """
    from db.schema import init_db
    from db.coupon import (
        upsert_coupon, upsert_fixture, add_coupon_fixture,
        upsert_tips, log_coupon_event,
    )
    from db.connection import get_conn

    init_db()
    game_days = fetch_game_days(debug=debug)
    if not game_days:
        return False

    now_utc = datetime.now(timezone.utc).isoformat()
    ingested = 0

    for gd in game_days:
        key            = gd["key"]
        coupon_id      = f"{key}-{week:02d}-{year}"
        label_suffix   = f" — frist {gd['deadline'][:10]}" if gd.get("deadline") else ""
        label          = f"{_DAY_TYPE_TO_LABEL.get(key, key)}{label_suffix}"
        deadline       = gd["deadline"]
        matches        = gd["matches"]

        # Change detection (skipped when force_refresh=True)
        new_hash = _content_hash(matches)
        from db.coupon import list_coupons
        existing = next(
            (c for c in list_coupons(week=week, year=year)
             if c["coupon_id"] == coupon_id),
            None,
        )
        if existing and existing.get("content_hash") == new_hash and not force_refresh:
            # Fixture data unchanged — but always update omsetning and tips (both change continuously).
            if gd.get("omsetning") is not None:
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE coupons SET omsetning=?, updated_at=datetime('now') WHERE coupon_id=?",
                        (gd["omsetning"], coupon_id),
                    )
            # Public tip percentages change continuously as users vote — update them
            # even when the fixture structure (match IDs / teams / kickoff) is unchanged.
            n_tip_changes = 0
            for m in matches:
                with get_conn() as conn:
                    row = conn.execute(
                        """SELECT cf.fixture_id,
                                  cf.public_h, cf.public_u, cf.public_b,
                                  cf.expert_h, cf.expert_u, cf.expert_b
                           FROM coupon_fixtures cf
                           JOIN fixtures f ON f.fixture_id = cf.fixture_id
                           WHERE cf.coupon_id = ? AND f.nt_match_id = ?""",
                        (coupon_id, m["nt_match_id"]),
                    ).fetchone()
                if not row:
                    continue
                before = (row["public_h"], row["public_u"], row["public_b"])
                after  = (m["public_h"],  m["public_u"],  m["public_b"])
                if before != after:
                    print(
                        f"  nt: tips updated  {m['home_name']} vs {m['away_name']}"
                        f"  public before H{before[0]} U{before[1]} B{before[2]}"
                        f"  → after H{after[0]} U{after[1]} B{after[2]}"
                    )
                    n_tip_changes += 1
                upsert_tips(
                    coupon_id=coupon_id,
                    fixture_id=row["fixture_id"],
                    expert_h=m["expert_h"],
                    expert_u=m["expert_u"],
                    expert_b=m["expert_b"],
                    public_h=m["public_h"],
                    public_u=m["public_u"],
                    public_b=m["public_b"],
                )
            print(
                f"  nt: {coupon_id} fixtures unchanged — "
                f"tips updated ({n_tip_changes} fixture(s) changed)."
            )
            ingested += 1
            continue

        if existing:
            log_coupon_event(coupon_id, "fixture_changed",
                             {"old_hash": existing.get("content_hash"), "new_hash": new_hash})

        # Always clear old coupon_fixtures before writing new ones so that removed
        # or replaced matches do not accumulate. Predictions are never touched.
        if existing:
            with get_conn() as conn:
                conn.execute(
                    "DELETE FROM coupon_fixtures WHERE coupon_id = ?",
                    (coupon_id,),
                )

        upsert_coupon(
            coupon_id=coupon_id,
            label=label,
            deadline_utc=deadline,
            week=week,
            year=year,
            nt_game_day_id=gd.get("nt_game_day_id"),
            day_type=gd["day_type"],
            source="nt_api",
            confidence="verified",
            content_hash=new_hash,
            last_synced_at=now_utc,
            omsetning=gd.get("omsetning"),
        )
        if not existing:
            log_coupon_event(coupon_id, "created", {"source": "nt_api", "matches": len(matches)})

        for m in matches:
            home_team_id = _resolve_or_create_team(
                nt_team_id=m["home_nt_team_id"],
                betradar_id=m["home_betradar_id"],
                name_local=m["home_name"],
                arrangement_name=m["arrangement_name"],
                country_iso=m["home_country_iso"],
            )
            away_team_id = _resolve_or_create_team(
                nt_team_id=m["away_nt_team_id"],
                betradar_id=m["away_betradar_id"],
                name_local=m["away_name"],
                arrangement_name=m["arrangement_name"],
                country_iso=m["away_country_iso"],
            )

            fixture_id = upsert_fixture(
                home_team_id=home_team_id,
                away_team_id=away_team_id,
                competition_id="international-friendly-m",  # placeholder; refined later
                kickoff_utc=m["kickoff_utc"],
                nt_match_id=m["nt_match_id"],
                betradar_match_id=m["betradar_match_id"],
                arrangement_name=m["arrangement_name"],
                source="nt_api",
            )

            add_coupon_fixture(
                coupon_id=coupon_id,
                fixture_id=fixture_id,
                match_number=m["match_number"],
                arrangement_name=m["arrangement_name"],
            )

            upsert_tips(
                coupon_id=coupon_id,
                fixture_id=fixture_id,
                expert_h=m["expert_h"],
                expert_u=m["expert_u"],
                expert_b=m["expert_b"],
                public_h=m["public_h"],
                public_u=m["public_u"],
                public_b=m["public_b"],
            )

        n = len(matches)
        print(f"  nt: {coupon_id} — {n} fixture(s), source=nt_api")
        ingested += 1

    return ingested > 0
