"""
NT Oddsen odds scraper — EXPERIMENTAL / DEV-ONLY.  Not used in production.

Tested via Firecrawl on 2026-06-30: match metadata renders from SSR, but
odds never load.  The Sportradar SIR widget fetches odds via an authenticated
WebSocket to feed.mapi.sportradar.com (Sportradar commercial feed, not public).
All match rows carry the CSS class "sh-match__matchList-wrapper--no-odds" when
the feed is inaccessible.  NT does not expose a public odds API.

NT Oddsen direct ingestion is parked until a stable odds source exists.
This module must NOT be imported by production code paths (backend/main.py,
backend/scheduler.py, sync.py).  Use it only for local experiments:
    python scripts/test_nt_oddsen_scan.py

Stores each scraped selection as a row in nt_oddsen_odds_snapshot.
Reads FIRECRAWL_API_KEY from environment or .env.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── .env loader ───────────────────────────────────────────────────────────────

def _load_dotenv(path: str = ".env") -> None:
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_dotenv()

NT_FOOTBALL_URL = "https://s5.sir.sportradar.com/norsktipping/no/sport/1"
NT_BOOKMAKER_LABEL = "NT Oddsen"

_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "home_team":       {"type": "string"},
                    "away_team":       {"type": "string"},
                    "league":          {"type": "string"},
                    "kickoff":         {"type": "string"},
                    "home_odds":       {"type": "number"},
                    "draw_odds":       {"type": "number"},
                    "away_odds":       {"type": "number"},
                    "btts_yes_odds":   {"type": "number"},
                    "btts_no_odds":    {"type": "number"},
                    "over_2_5_odds":   {"type": "number"},
                    "under_2_5_odds":  {"type": "number"},
                },
                "required": ["home_team", "away_team"],
            },
        },
    },
    "required": ["matches"],
}

_EXTRACTION_PROMPT = (
    "This is a Norsk Tipping sports betting page (Sportradar SIR widget) showing "
    "upcoming football matches with decimal odds. "
    "Extract all visible football matches with their odds. "
    "For each match extract: home and away team names (Norwegian as shown on page), "
    "league/tournament name, kickoff time, and all available decimal odds: "
    "1X2 (home win / draw / away win), BTTS yes/no, over 2.5 goals / under 2.5 goals. "
    "Only include numeric decimal odds values. "
    "Skip any match where you cannot find at least the 1X2 home/draw/away odds."
)

# ── Name normalization ────────────────────────────────────────────────────────

# Norwegian → English national team name map (lowercase normalized)
_NO_TO_EN: dict[str, str] = {
    "spania": "spain",
    "frankrike": "france",
    "tyskland": "germany",
    "italia": "italy",
    "nederland": "netherlands",
    "belgia": "belgium",
    "sveits": "switzerland",
    "osterrike": "austria",
    "tsjekkia": "czech republic",
    "kroatia": "croatia",
    "serbias": "serbia",
    "ungarn": "hungary",
    "albanias": "albania",
    "skottland": "scotland",
    "norge": "norway",
    "sverige": "sweden",
    "danmark": "denmark",
    "island": "iceland",
    "brasil": "brazil",
    "sordkorea": "south korea",
    "saudi-arabia": "saudi arabia",
    "saudiarabia": "saudi arabia",
    "usa": "united states",
    "storbritannia": "great britain",
    "marokko": "morocco",
}

# Strip only org-type suffixes (not words that differentiate clubs like "united"/"city")
_SUFFIX_RE = re.compile(
    r"\b(fc|fk|if|bk|sk|aik|ik|il|cf|sc|ss)\b"
)


def normalize_team_name(name: str) -> str:
    """Lowercase, strip diacritics, remove common suffixes, apply NO→EN map."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    ascii_str = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    ascii_str = _SUFFIX_RE.sub("", ascii_str)
    ascii_str = re.sub(r"[^a-z0-9 ]", "", ascii_str)
    ascii_str = re.sub(r"\s+", " ", ascii_str).strip()
    return _NO_TO_EN.get(ascii_str, ascii_str)


def make_fixture_key(home: str, away: str, kickoff_date: str | None = None) -> str:
    """Canonical lookup key: normalize(home)|normalize(away)|YYYY-MM-DD."""
    h = normalize_team_name(home)
    a = normalize_team_name(away)
    d = (kickoff_date or "")[:10]
    return f"{h}|{a}|{d}"


# ── Kickoff parsing ───────────────────────────────────────────────────────────

_MO_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}


def _parse_kickoff_iso(kickoff_str: str | None) -> str | None:
    if not kickoff_str:
        return None
    s = kickoff_str.strip()
    # Already ISO
    if re.match(r"\d{4}-\d{2}-\d{2}", s):
        return s[:16]
    # "dd.mm.yyyy HH:MM" or "dd.mm HH:MM"
    m = re.match(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{4}))?\s+(\d{2}:\d{2})", s)
    if m:
        d, mo, yr, t = m.groups()
        yr = yr or str(datetime.now().year)
        return f"{yr}-{int(mo):02d}-{int(d):02d}T{t}:00"
    # "dd. mon HH:MM" e.g. "30. jun 21:00"
    m2 = re.match(r"(\d{1,2})\.\s+([a-z]{3})\s+(\d{2}:\d{2})", s.lower())
    if m2:
        d, mon, t = m2.groups()
        mo_num = _MO_MAP.get(mon, 0)
        if mo_num:
            yr = datetime.now().year
            return f"{yr}-{mo_num:02d}-{int(d):02d}T{t}:00"
    return None


# ── DB helpers ────────────────────────────────────────────────────────────────

_DDL_NT_ODDSEN = """
CREATE TABLE IF NOT EXISTS nt_oddsen_odds_snapshot (
    id               TEXT    PRIMARY KEY,
    scraped_at       TEXT    NOT NULL,
    source_url       TEXT    NOT NULL,
    fixture_key      TEXT    NOT NULL,
    home_team        TEXT    NOT NULL,
    away_team        TEXT    NOT NULL,
    league           TEXT,
    kickoff_iso      TEXT,
    market           TEXT    NOT NULL,
    selection        TEXT    NOT NULL,
    odds             REAL    NOT NULL,
    raw_json         TEXT,
    confidence_score REAL    DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_nt_oddsen_key
    ON nt_oddsen_odds_snapshot(fixture_key, market, selection, scraped_at);
CREATE INDEX IF NOT EXISTS idx_nt_oddsen_scraped
    ON nt_oddsen_odds_snapshot(scraped_at);
"""


def ensure_table(conn) -> None:
    conn.executescript(_DDL_NT_ODDSEN)


def _store_snapshot(conn, rows: list[dict]) -> int:
    stored = 0
    for row in rows:
        conn.execute(
            """INSERT OR IGNORE INTO nt_oddsen_odds_snapshot
               (id, scraped_at, source_url, fixture_key, home_team, away_team,
                league, kickoff_iso, market, selection, odds, raw_json, confidence_score)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                row["scraped_at"],
                row["source_url"],
                row["fixture_key"],
                row["home_team"],
                row["away_team"],
                row.get("league"),
                row.get("kickoff_iso"),
                row["market"],
                row["selection"],
                row["odds"],
                row.get("raw_json"),
                row.get("confidence_score", 1.0),
            ),
        )
        stored += 1
    return stored


def get_nt_odds_for_fixture(
    conn,
    home_name: str,
    away_name: str,
    kickoff_utc: str | None,
    max_age_hours: int = 6,
) -> dict:
    """
    Return NT Oddsen odds for a fixture as:
      {"1x2": {"H": float, "U": float, "B": float}, "btts": {...}, "over_2.5": {...}}

    Only includes markets where all required selections are present.
    Returns empty dict if nothing found or snapshot is stale.
    """
    ko_date = (kickoff_utc or "")[:10]
    fixture_key = make_fixture_key(home_name, away_name, ko_date)

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    rows = conn.execute(
        """SELECT market, selection, odds
           FROM nt_oddsen_odds_snapshot
           WHERE fixture_key = ? AND scraped_at >= ?
           ORDER BY scraped_at DESC""",
        (fixture_key, cutoff),
    ).fetchall()

    # Collect per market, keeping latest per selection
    raw: dict[str, dict[str, float]] = {}
    for r in rows:
        mk = r["market"]
        sel = r["selection"]
        if mk not in raw:
            raw[mk] = {}
        if sel not in raw[mk]:
            raw[mk][sel] = float(r["odds"])

    result: dict[str, dict] = {}
    if all(s in raw.get("1x2", {}) for s in ("H", "U", "B")):
        result["1x2"] = {s: raw["1x2"][s] for s in ("H", "U", "B")}
    if all(s in raw.get("btts", {}) for s in ("yes", "no")):
        result["btts"] = {s: raw["btts"][s] for s in ("yes", "no")}
    if all(s in raw.get("over_2.5", {}) for s in ("over", "under")):
        result["over_2.5"] = {s: raw["over_2.5"][s] for s in ("over", "under")}
    return result


def load_nt_odds_bulk(conn, max_age_hours: int = 6) -> dict[str, dict[str, dict[str, float]]]:
    """
    Load all recent NT Oddsen rows into memory as:
      {fixture_key: {market: {selection: odds}}}

    Used by generate_global_bet_candidates for bulk lookup.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        rows = conn.execute(
            """SELECT fixture_key, market, selection, odds
               FROM nt_oddsen_odds_snapshot
               WHERE scraped_at >= ?
               ORDER BY scraped_at DESC""",
            (cutoff,),
        ).fetchall()
    except Exception:
        return {}

    nt_map: dict[str, dict[str, dict[str, float]]] = {}
    for r in rows:
        fk = r["fixture_key"]
        mk = r["market"]
        sel = r["selection"]
        if fk not in nt_map:
            nt_map[fk] = {}
        if mk not in nt_map[fk]:
            nt_map[fk][mk] = {}
        if sel not in nt_map[fk][mk]:  # keep most recent only (ORDER BY scraped_at DESC)
            nt_map[fk][mk][sel] = float(r["odds"])

    return nt_map


# ── Parse LLM extract output → DB rows ───────────────────────────────────────

def _extract_rows(match_data: list[dict], scraped_at: str, source_url: str) -> list[dict]:
    rows: list[dict] = []
    for m in match_data:
        home = (m.get("home_team") or "").strip()
        away = (m.get("away_team") or "").strip()
        if not home or not away:
            continue

        ko_iso = _parse_kickoff_iso(m.get("kickoff"))
        ko_date = (ko_iso or "")[:10]
        raw = json.dumps(m, ensure_ascii=False)

        base = {
            "scraped_at":      scraped_at,
            "source_url":      source_url,
            "fixture_key":     make_fixture_key(home, away, ko_date),
            "home_team":       home,
            "away_team":       away,
            "league":          m.get("league") or None,
            "kickoff_iso":     ko_iso,
            "raw_json":        raw,
            "confidence_score": 1.0,
        }

        def _add(market: str, sel: str, val) -> None:
            if val and isinstance(val, (int, float)) and 1.01 <= float(val) <= 200:
                rows.append({**base, "market": market, "selection": sel, "odds": float(val)})

        _add("1x2", "H", m.get("home_odds"))
        _add("1x2", "U", m.get("draw_odds"))
        _add("1x2", "B", m.get("away_odds"))
        _add("btts", "yes", m.get("btts_yes_odds"))
        _add("btts", "no",  m.get("btts_no_odds"))
        _add("over_2.5", "over",  m.get("over_2_5_odds"))
        _add("over_2.5", "under", m.get("under_2_5_odds"))

    return rows


# ── Main scrape function ──────────────────────────────────────────────────────

def scrape_nt_oddsen(wait_ms: int = 5000, verbose: bool = True) -> dict:
    """
    Scrape NT Oddsen football odds via Firecrawl LLM extract and store in DB.

    Returns summary dict: {n_matches, n_rows_stored, markets_found, scraped_at, error?}
    If FIRECRAWL_API_KEY is not set, returns {error: "no_api_key"} without raising.
    """
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        msg = "FIRECRAWL_API_KEY not set — NT Oddsen scrape skipped"
        if verbose:
            print(f"[NT Oddsen] {msg}")
        return {"error": "no_api_key", "message": msg, "n_matches": 0, "n_rows_stored": 0}

    try:
        from firecrawl import V1FirecrawlApp, V1JsonConfig
    except ImportError:
        msg = "firecrawl-py not installed — run: pip install firecrawl-py"
        return {"error": "firecrawl_not_installed", "message": msg, "n_matches": 0, "n_rows_stored": 0}

    app = V1FirecrawlApp(api_key=api_key)
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if verbose:
        print(f"[NT Oddsen] Scraping {NT_FOOTBALL_URL} (JS wait={wait_ms}ms)...")

    try:
        result = app.scrape_url(
            NT_FOOTBALL_URL,
            formats=["json"],
            wait_for=wait_ms,
            timeout=120000,  # 120s Firecrawl job timeout → 125s HTTP read timeout
            json_options=V1JsonConfig(
                prompt=_EXTRACTION_PROMPT,
                schema_field=_EXTRACTION_SCHEMA,
            ),
        )
    except Exception as exc:
        return {"error": "scrape_failed", "message": str(exc), "n_matches": 0, "n_rows_stored": 0}

    # v4 SDK: structured data in result.json_field (aliased from "json" in response)
    extracted = result.json_field or result.extract or {}
    if isinstance(extracted, dict):
        matches = extracted.get("matches") or []
    else:
        matches = []

    if verbose:
        print(f"[NT Oddsen] LLM extracted {len(matches)} matches")

    rows = _extract_rows(matches, scraped_at, NT_FOOTBALL_URL)

    from db.connection import get_conn
    conn = get_conn()
    ensure_table(conn)
    stored = _store_snapshot(conn, rows)
    conn.commit()
    conn.close()

    markets_found: dict[str, int] = {}
    for r in rows:
        markets_found[r["market"]] = markets_found.get(r["market"], 0) + 1

    if verbose:
        print(f"[NT Oddsen] Stored {stored} rows  markets={markets_found}")

    return {
        "n_matches":    len(matches),
        "n_rows_stored": stored,
        "markets_found": markets_found,
        "scraped_at":   scraped_at,
        "source_url":   NT_FOOTBALL_URL,
    }
