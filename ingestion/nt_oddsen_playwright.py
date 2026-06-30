"""
NT Oddsen Playwright scraper -- production-safe 1X2 odds ingestion.

Scrapes https://www.norsk-tipping.no/sport/oddsen using headless Chromium.
The sportsbook loads in an iframe (same-origin: /sport/oddsen/sportsbook/).
1X2 odds render immediately as div[data-for="selection-event-ID.1"] with
aria-label="TeamName, odds X.XX" -- no login, no Sportradar auth required.

Architecture note:
  This module is PRODUCTION code.  It does NOT use Firecrawl.
  It may be imported by backend/main.py, backend/scheduler.py, sync.py.

Requires:
  playwright Python package + Chromium browser:
    pip install playwright
    python -m playwright install chromium
  Returns {error: "playwright_not_installed"} gracefully if missing.

Stores results in: nt_oddsen_odds_snapshot (shared with nt_oddsen_scraper.py)
"""
from __future__ import annotations

import json
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

NT_SPORTSBOOK_URL = "https://www.norsk-tipping.no/sport/oddsen"
NT_BOOKMAKER_LABEL = "NT Oddsen"

# ---- Name normalisation (self-contained, matches nt_oddsen_scraper.py) ------

# Norwegian → English national team name map
_NO_TO_EN: dict[str, str] = {
    "spania":          "spain",
    "frankrike":       "france",
    "tyskland":        "germany",
    "italia":          "italy",
    "nederland":       "netherlands",
    "belgia":          "belgium",
    "sveits":          "switzerland",
    "osterrike":       "austria",
    "osterreich":      "austria",
    "tsjekkia":        "czech republic",
    "kroatia":         "croatia",
    "serbias":         "serbia",
    "ungarn":          "hungary",
    "albanias":        "albania",
    "skottland":       "scotland",
    "norge":           "norway",
    "sverige":         "sweden",
    "danmark":         "denmark",
    "island":          "iceland",
    "brasil":          "brazil",
    "sordkorea":       "south korea",
    "saudi-arabia":    "saudi arabia",
    "saudiarabia":     "saudi arabia",
    "usa":             "united states",
    "storbritannia":   "great britain",
    "marokko":         "morocco",
    "elfenbenskysten": "ivory coast",
    "dr kongo":        "dr congo",
    "kongodr":         "dr congo",
    "congo dr":        "dr congo",   # AF name "Congo DR"; NT name "DR Kongo"
    "kongo":           "congo",
    "algerie":         "algeria",
    "kamerun":         "cameroon",
    "nigeria":         "nigeria",
    "etopia":          "ethiopia",
    "de forente arabiske emirater": "united arab emirates",
    "forente arabiske emirater":    "united arab emirates",
    "de forente stater":            "united states",
    "slovakias":       "slovakia",
    "osterrikisk":     "austria",
    "sveitsisk":       "switzerland",
    "tyrkia":          "turkey",
    "russland":        "russia",
    "hviterussland":   "belarus",
    "ukraina":         "ukraine",
    "moldova":         "moldova",
    "wales":           "wales",
    "nord-irland":     "northern ireland",
    "irland":          "ireland",
    # Bosnia: NT "Bosnia-Hercegovina" strips hyphen -> "bosniahercegovina";
    #         AF "Bosnia & Herzegovina" strips & -> "bosnia herzegovina"
    "bosniahercegovina":      "bosnia and herzegovina",
    "bosnia herzegovina":     "bosnia and herzegovina",
    "bosnia and hercegovina": "bosnia and herzegovina",
    # Cape Verde: NT "Kapp Verde"
    "kapp verde":      "cape verde",
}

_SUFFIX_RE = re.compile(r"\b(fc|fk|if|bk|sk|aik|ik|il|cf|sc|ss)\b")

_ARIA_ODDS_RE = re.compile(r"odds\s+([\d]+\.[\d]{1,2})", re.IGNORECASE)


def normalize_team_name(name: str) -> str:
    """Lowercase, strip diacritics, remove org suffixes, apply NO->EN map."""
    if not name:
        return ""
    nfkd = unicodedata.normalize("NFKD", name.lower().strip())
    s = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return _NO_TO_EN.get(s, s)


def make_fixture_key(home: str, away: str, kickoff_date: str | None = None) -> str:
    """Canonical lookup key: normalize(home)|normalize(away)|YYYY-MM-DD."""
    return f"{normalize_team_name(home)}|{normalize_team_name(away)}|{(kickoff_date or '')[:10]}"


# ---- Kickoff parsing --------------------------------------------------------

_MO_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "mai": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "des": 12,
}

# NT kickoff format: "Tir.  30/6 19:00"  or  "Ons. 1/7 03:00"
_KO_RE = re.compile(
    r"(\d{1,2})/(\d{1,2})\s+(\d{2}:\d{2})"  # "30/6 19:00"
)


def _parse_nt_kickoff(text: str) -> str | None:
    """Parse NT kickoff string to ISO date-time (local time, no tz)."""
    if not text:
        return None
    m = _KO_RE.search(text)
    if m:
        day, month, time_str = m.groups()
        year = datetime.now().year
        return f"{year}-{int(month):02d}-{int(day):02d}T{time_str}:00"
    return None


# ---- DB helpers -------------------------------------------------------------

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


def store_nt_snapshot(conn, rows: list[dict]) -> int:
    """Insert rows into nt_oddsen_odds_snapshot. Skips duplicates (INSERT OR IGNORE)."""
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


def load_nt_odds_bulk(conn, max_age_hours: int = 6) -> dict[str, dict[str, float]]:
    """
    Load all recent NT Oddsen 1X2 rows into memory as:
      { fixture_key: {"H": float, "U": float, "B": float} }

    Only includes fixtures where all 3 selections (H, U, B) are present.
    Returns {} gracefully if the table does not exist yet.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max_age_hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        rows = conn.execute(
            """SELECT fixture_key, selection, odds
               FROM nt_oddsen_odds_snapshot
               WHERE market = '1x2' AND scraped_at >= ?
               ORDER BY scraped_at DESC""",
            (cutoff,),
        ).fetchall()
    except Exception:
        return {}

    # Aggregate per fixture_key; keep most-recent per selection
    raw: dict[str, dict[str, float]] = {}
    for r in rows:
        fk  = r["fixture_key"]
        sel = r["selection"]
        if fk not in raw:
            raw[fk] = {}
        if sel not in raw[fk]:  # most-recent first (ORDER BY DESC)
            raw[fk][sel] = float(r["odds"])

    # Only return fixtures with all 3 selections
    result: dict[str, dict[str, float]] = {}
    for fk, sels in raw.items():
        if all(s in sels for s in ("H", "U", "B")):
            result[fk] = {"H": sels["H"], "U": sels["U"], "B": sels["B"]}

    return result


# ---- Scraper ----------------------------------------------------------------

def scrape_nt_oddsen_playwright(
    verbose: bool = True,
    settle_ms: int = 5_000,
    timeout_ms: int = 30_000,
) -> dict:
    """
    Scrape NT Oddsen football 1X2 odds via headless Playwright Chromium.

    Navigates to https://www.norsk-tipping.no/sport/oddsen, switches into
    the sportsbook iframe, waits for selection-event divs to appear, then
    extracts team names, kickoff times, leagues, and H/U/B odds.

    Returns:
        {
          "n_matches":     int,
          "n_rows_stored": int,
          "scraped_at":    ISO str,
          "matches":       list of match dicts,
          "error":         str | None,
        }

    If playwright is not installed, returns {"error": "playwright_not_installed"}.
    All errors are caught; the function never raises.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        msg = "playwright not installed -- run: pip install playwright && python -m playwright install chromium"
        if verbose:
            print(f"[NT Playwright] {msg}")
        return {"error": "playwright_not_installed", "message": msg,
                "n_matches": 0, "n_rows_stored": 0, "matches": []}

    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if verbose:
        print(f"[NT Playwright] Scraping {NT_SPORTSBOOK_URL}...")

    matches_extracted: list[dict] = []
    error_msg: str | None = None

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
            )
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="nb-NO",
            )
            page = ctx.new_page()

            # Navigate
            page.goto(NT_SPORTSBOOK_URL, wait_until="domcontentloaded", timeout=30_000)

            # Find sportsbook iframe
            try:
                page.wait_for_selector("iframe#sportsbookid", timeout=15_000)
            except PWTimeout:
                raise RuntimeError("iframe#sportsbookid not found after 15s")

            el = page.query_selector("iframe#sportsbookid")
            if not el:
                raise RuntimeError("iframe#sportsbookid element returned None")

            sb_frame = el.content_frame()
            if not sb_frame:
                raise RuntimeError("iframe has no content frame")

            # Wait for selection divs to appear in the iframe
            try:
                sb_frame.wait_for_selector(
                    "[data-for^='selection-event-']",
                    timeout=timeout_ms,
                )
            except PWTimeout:
                raise RuntimeError(f"No selection-event divs after {timeout_ms//1000}s")

            # Let WebSocket data settle
            page.wait_for_timeout(settle_ms)

            # Extract metadata (teams/kickoff/league) from EventContainers
            containers = sb_frame.query_selector_all("[class*='EventContainer']")
            meta_list: list[dict] = []
            for c in containers:
                try:
                    team_els = c.query_selector_all("[class*='ParticipantNameItem']")
                    teams    = [(t.inner_text() or "").strip() for t in team_els]
                    if len(teams) < 2:
                        continue
                    kickoff_raw = ""
                    dt = c.query_selector("[class*='DateContainer']")
                    if dt:
                        kickoff_raw = (dt.inner_text() or "").strip()
                    league_str = ""
                    lg = c.query_selector("[class*='TournamentNameItem']")
                    if lg:
                        league_str = (lg.inner_text() or "").strip()
                    meta_list.append({
                        "home": teams[0],
                        "away": teams[1],
                        "kickoff_raw": kickoff_raw,
                        "league": league_str,
                    })
                except Exception:
                    pass

            # Extract all selections in DOM order
            sel_divs = sb_frame.query_selector_all("[data-for^='selection-event-']")
            selections: list[dict[str, Any]] = []
            for div in sel_divs:
                aria    = div.get_attribute("aria-label") or ""
                data_for = div.get_attribute("data-for") or ""
                m2 = _ARIA_ODDS_RE.search(aria)
                if not m2:
                    continue
                odds_v = float(m2.group(1))
                if not (1.01 <= odds_v <= 99.0):
                    continue
                label = aria.split(",")[0].strip()
                selections.append({"label": label, "odds": odds_v, "data_for": data_for})

            browser.close()

            # Group selections into triples (H, U, B per match, in DOM order)
            n_meta = len(meta_list)
            for i, group_start in enumerate(range(0, len(selections) - 2, 3)):
                trio = selections[group_start:group_start + 3]
                if len(trio) < 3:
                    break

                # Team/date/league from metadata (by index); fall back to aria labels
                if i < n_meta:
                    home    = meta_list[i]["home"]
                    away    = meta_list[i]["away"]
                    ko_raw  = meta_list[i]["kickoff_raw"]
                    league  = meta_list[i]["league"]
                else:
                    home    = trio[0]["label"]
                    away    = trio[2]["label"]
                    ko_raw  = ""
                    league  = ""

                ko_iso  = _parse_nt_kickoff(ko_raw)
                ko_date = (ko_iso or "")[:10]

                matches_extracted.append({
                    "home_team":   home,
                    "away_team":   away,
                    "league":      league,
                    "kickoff_raw": ko_raw,
                    "kickoff_iso": ko_iso,
                    "kickoff_date": ko_date,
                    "fixture_key": make_fixture_key(home, away, ko_date),
                    "odds_h":      trio[0]["odds"],
                    "odds_u":      trio[1]["odds"],
                    "odds_b":      trio[2]["odds"],
                    "sel_labels":  [s["label"] for s in trio],
                })

    except Exception as exc:
        error_msg = str(exc)
        if verbose:
            print(f"[NT Playwright] ERROR: {exc}")

    if verbose and matches_extracted:
        print(f"[NT Playwright] Extracted {len(matches_extracted)} matches")

    # Build DB rows and store
    rows: list[dict] = []
    for m in matches_extracted:
        raw_json = json.dumps({
            "home": m["home_team"], "away": m["away_team"],
            "league": m["league"], "kickoff_raw": m["kickoff_raw"],
            "H": m["odds_h"], "U": m["odds_u"], "B": m["odds_b"],
        }, ensure_ascii=False)
        base = {
            "scraped_at":    scraped_at,
            "source_url":    NT_SPORTSBOOK_URL,
            "fixture_key":   m["fixture_key"],
            "home_team":     m["home_team"],
            "away_team":     m["away_team"],
            "league":        m["league"] or None,
            "kickoff_iso":   m["kickoff_iso"],
            "market":        "1x2",
            "raw_json":      raw_json,
            "confidence_score": 1.0,
        }
        rows.append({**base, "selection": "H", "odds": m["odds_h"]})
        rows.append({**base, "selection": "U", "odds": m["odds_u"]})
        rows.append({**base, "selection": "B", "odds": m["odds_b"]})

    n_stored = 0
    if rows:
        try:
            from db.connection import get_conn
            conn = get_conn()
            ensure_table(conn)
            n_stored = store_nt_snapshot(conn, rows)
            conn.commit()
            conn.close()
        except Exception as exc:
            if verbose:
                print(f"[NT Playwright] DB store error: {exc}")
            error_msg = error_msg or str(exc)

    if verbose and n_stored:
        print(f"[NT Playwright] Stored {n_stored} rows ({len(matches_extracted)} matches)")

    return {
        "n_matches":     len(matches_extracted),
        "n_rows_stored": n_stored,
        "scraped_at":    scraped_at,
        "matches":       matches_extracted,
        "error":         error_msg,
    }
