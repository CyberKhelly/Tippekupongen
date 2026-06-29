"""
API-Football odds ingestion — 1X2 fallback + multi-market odds (BTTS, Over/Under).

One AF /odds call per fixture fetches all markets simultaneously.

1X2 storage: `odds` table — written only when no odds row exists (any source).
BTTS / Over/Under: `odds_markets` table — upserted on every run (latest wins).

Bookmaker priority for both: Bet365 → William Hill → Marathonbet → 10Bet → first available.

Usage:
    from ingestion.api_football_odds import ingest_af_odds_fallback
    summary = ingest_af_odds_fallback(week=24, year=2026)

    from ingestion.api_football_odds import scan_af_market_odds
    summary = scan_af_market_odds(lookahead_hours=48)   # global league scan
"""
from __future__ import annotations

import json
import time
import uuid
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from config import API_FOOTBALL_KEY

_BASE    = "https://v3.football.api-sports.io"
_DELAY   = 2.1   # seconds between requests (AF rate limit: 30/min)
_TIMEOUT = 15    # socket timeout

# Bookmaker preference order (AF canonical names)
_PREFERRED = ["Bet365", "William Hill", "Marathonbet", "10Bet"]

# Normalised market definitions
# AF name → (market_key, market_display_name)
_MARKET_KEYS: dict[str, tuple[str, str]] = {
    "Match Winner":     ("1X2",        "Match Winner"),
    "1X2":              ("1X2",        "Match Winner"),
    "Both Teams Score": ("BTTS",       "Both Teams Score"),
    "Goals Over/Under": ("OVER_UNDER", "Goals Over/Under"),
}

# Selections within each market_key (AF value → normalised selection label)
_1X2_SEL   = {"Home": "HOME", "Draw": "DRAW", "Away": "AWAY"}
_BTTS_SEL  = {"Yes": "YES",   "No":   "NO"}

# Over/Under: we only care about the 2.5 line
_OU_LINE   = 2.5
_OU_OVER   = {"Over 2.5", "Over(2.5)"}
_OU_UNDER  = {"Under 2.5", "Under(2.5)"}


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_json(path: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        raise EnvironmentError("API_FOOTBALL_KEY not set")
    qs  = urllib.parse.urlencode(params)
    url = f"{_BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"x-apisports-key": API_FOOTBALL_KEY})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


# ── Market parsing ────────────────────────────────────────────────────────────

def _parse_bookmakers(data: dict) -> dict[str, dict[str, list[dict]]]:
    """
    Parse raw AF /odds response into:
        {bookmaker_name: {market_key: [{selection, line, odds}, ...]}}
    """
    result: dict[str, dict[str, list[dict]]] = {}
    for item in data.get("response", []):
        for bookie in item.get("bookmakers", []):
            bname = bookie.get("name", "").strip()
            if not bname:
                continue
            if bname not in result:
                result[bname] = {}
            for bet in bookie.get("bets", []):
                bet_name = bet.get("name", "")
                if bet_name not in _MARKET_KEYS:
                    continue
                market_key, market_name = _MARKET_KEYS[bet_name]

                vals = {v["value"]: v["odd"] for v in bet.get("values", [])}

                if market_key == "1X2" and market_key not in result[bname]:
                    rows = []
                    for af_val, sel in _1X2_SEL.items():
                        try:
                            o = float(vals[af_val])
                            if o > 1.0:
                                rows.append({"selection": sel, "line": None, "odds": o,
                                             "market_name": market_name})
                        except (KeyError, ValueError):
                            pass
                    if len(rows) == 3:
                        result[bname][market_key] = rows

                elif market_key == "BTTS" and market_key not in result[bname]:
                    rows = []
                    for af_val, sel in _BTTS_SEL.items():
                        try:
                            o = float(vals[af_val])
                            if o > 1.0:
                                rows.append({"selection": sel, "line": None, "odds": o,
                                             "market_name": market_name})
                        except (KeyError, ValueError):
                            pass
                    if len(rows) == 2:
                        result[bname][market_key] = rows

                elif market_key == "OVER_UNDER" and market_key not in result[bname]:
                    over_odds = under_odds = None
                    for k, v in vals.items():
                        if k in _OU_OVER:
                            try:
                                over_odds = float(v)
                            except ValueError:
                                pass
                        elif k in _OU_UNDER:
                            try:
                                under_odds = float(v)
                            except ValueError:
                                pass
                    if over_odds and under_odds and over_odds > 1.0 and under_odds > 1.0:
                        result[bname][market_key] = [
                            {"selection": "OVER",  "line": _OU_LINE, "odds": over_odds,
                             "market_name": market_name},
                            {"selection": "UNDER", "line": _OU_LINE, "odds": under_odds,
                             "market_name": market_name},
                        ]
    return result


def _pick_best_markets(
    bookmakers: dict[str, dict[str, list[dict]]]
) -> dict[str, tuple[str, list[dict]]]:
    """
    For each market_key, pick the highest-priority bookmaker that has complete data.
    Returns {market_key: (bookmaker_name, [row_dicts])}
    """
    all_bkms = list(bookmakers.keys())
    ordered  = [b for b in _PREFERRED if b in bookmakers] + \
               [b for b in all_bkms if b not in _PREFERRED]

    best: dict[str, tuple[str, list[dict]]] = {}
    for bkm in ordered:
        for mkt, rows in bookmakers[bkm].items():
            if mkt not in best:
                best[mkt] = (bkm, rows)
    return best


def fetch_af_all_markets(
    af_fixture_id: int
) -> dict[str, tuple[str, list[dict]]] | None:
    """
    Call AF /odds for one fixture. Returns {market_key: (bookmaker, [rows])} or None.

    Market keys: "1X2", "BTTS", "OVER_UNDER"
    Each row dict: {selection, line, odds, market_name}
    """
    try:
        data = _get_json("odds", {"fixture": af_fixture_id})
    except Exception:
        return None

    errors = data.get("errors", {})
    if errors and errors not in ({}, []):
        return None
    if not data.get("response"):
        return None

    bkm_data = _parse_bookmakers(data)
    if not bkm_data:
        return None

    best = _pick_best_markets(bkm_data)
    return best if best else None


# ── Database write helpers ─────────────────────────────────────────────────────

def _store_market_odds(
    conn,
    fixture_id: str,
    af_fixture_id: int | None,
    best_markets: dict[str, tuple[str, list[dict]]],
    source: str = "api_football",
    verbose: bool = False,
) -> int:
    """
    Upsert BTTS and OVER_UNDER rows into odds_markets.
    Skips 1X2 (stored in the `odds` table instead).
    Returns number of rows inserted/updated.
    """
    now = _now_utc()
    n = 0
    for market_key, (bkm, rows) in best_markets.items():
        if market_key == "1X2":
            continue  # 1X2 goes in the odds table
        for row in rows:
            conn.execute(
                """INSERT INTO odds_markets
                   (id, fixture_id, af_fixture_id, bookmaker, market_name, market_key,
                    selection, line, odds, source, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(fixture_id, market_key, selection) DO UPDATE SET
                       bookmaker=excluded.bookmaker,
                       odds=excluded.odds,
                       line=excluded.line,
                       updated_at=excluded.updated_at""",
                (str(uuid.uuid4()), fixture_id, af_fixture_id, bkm,
                 row["market_name"], market_key, row["selection"],
                 row["line"], row["odds"], source, now),
            )
            n += 1
    return n


# ── Backward-compatible 1X2-only fetch (kept for other callers) ────────────────

def fetch_af_1x2(af_fixture_id: int) -> tuple[float, float, float, str] | None:
    """
    Returns (odds_h, odds_u, odds_b, bookmaker) from AF /odds or None.
    Prefer bookmakers in _PREFERRED order.
    """
    result = fetch_af_all_markets(af_fixture_id)
    if not result or "1X2" not in result:
        return None
    bkm, rows = result["1X2"]
    sel_map = {r["selection"]: r["odds"] for r in rows}
    try:
        return sel_map["HOME"], sel_map["DRAW"], sel_map["AWAY"], bkm
    except KeyError:
        return None


# ── Main ingestion function ───────────────────────────────────────────────────

def ingest_af_odds_fallback(
    week: int,
    year: int,
    verbose: bool = True,
) -> dict:
    """
    Fetch AF /odds for coupon fixtures with an AF link.

    One API call per fixture fetches all markets.
    1X2 → `odds` table (skip if any odds already exist).
    BTTS / OVER_UNDER → `odds_markets` table (upserted every run).

    Returns a summary dict:
        n_total         — total fixtures for the week
        n_no_af_link    — skipped: no AF fixture link
        n_skipped       — nothing needed for this fixture (all complete)
        n_1x2_filled    — new 1X2 odds inserted
        n_markets_rows  — odds_markets rows inserted/updated
        n_no_data       — AF returned nothing (odds not yet available)
        n_failed        — API errors
    """
    from db.connection import get_conn
    from db.coupon import list_coupons, get_coupon_matches, upsert_odds

    if not API_FOOTBALL_KEY:
        if verbose:
            print("  AF odds: API_FOOTBALL_KEY not set — skipping.")
        return {"n_total": 0, "n_no_af_link": 0, "n_skipped": 0,
                "n_1x2_filled": 0, "n_markets_rows": 0, "n_no_data": 0, "n_failed": 0}

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Deduplicate fixtures across all coupons for this week
    seen: set[str] = set()
    all_fixtures: list[dict] = []
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            fid = m["fixture_id"]
            if fid not in seen:
                seen.add(fid)
                all_fixtures.append(m)

    conn = get_conn()

    def _has_1x2(fixture_id: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM odds WHERE fixture_id=?", (fixture_id,)
        ).fetchone() is not None

    def _has_market(fixture_id: str, market_key: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM odds_markets WHERE fixture_id=? AND market_key=? LIMIT 1",
            (fixture_id, market_key),
        ).fetchone()
        return row is not None

    def _af_link(fixture_id: str) -> int | None:
        row = conn.execute(
            "SELECT api_football_fixture_id FROM api_football_fixture_links WHERE fixture_id=?",
            (fixture_id,),
        ).fetchone()
        return row[0] if row else None

    n_total = len(all_fixtures)
    n_no_af_link = n_skipped = n_1x2_filled = n_markets_rows = n_no_data = n_failed = 0
    n_calls = 0

    for m in all_fixtures:
        fid   = m["fixture_id"]
        home  = m.get("home_name", "?")
        away  = m.get("away_name", "?")
        label = f"{home} vs {away}"

        af_id = _af_link(fid)
        if af_id is None:
            n_no_af_link += 1
            if verbose:
                print(f"  [SKIP]  {label:<46}  (no AF link)")
            continue

        already_1x2  = _has_1x2(fid)
        already_btts = _has_market(fid, "BTTS")
        already_ou   = _has_market(fid, "OVER_UNDER")

        if already_1x2 and already_btts and already_ou:
            n_skipped += 1
            if verbose:
                print(f"  [DONE]  {label:<46}  (all markets complete)")
            continue

        if n_calls > 0:
            time.sleep(_DELAY)
        n_calls += 1

        try:
            best = fetch_af_all_markets(af_id)
        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f"  [ERR]   {label:<46}  {exc}")
            continue

        if not best:
            n_no_data += 1
            if verbose:
                print(f"  [NONE]  {label:<46}  (AF returned no odds)")
            continue

        parts: list[str] = []

        # ── 1X2 into odds table ──────────────────────────────────────────────
        if not already_1x2 and "1X2" in best:
            bkm, rows = best["1X2"]
            sel_map = {r["selection"]: r["odds"] for r in rows}
            try:
                h = sel_map["HOME"]
                u = sel_map["DRAW"]
                b = sel_map["AWAY"]
                upsert_odds(fid, "api_football", h, u, b)
                n_1x2_filled += 1
                parts.append(f"1X2 H={h:.2f} U={u:.2f} B={b:.2f} ({bkm})")
            except KeyError:
                pass
        elif already_1x2:
            parts.append("1X2 ✓")

        # ── BTTS / O/U into odds_markets ─────────────────────────────────────
        rows_written = _store_market_odds(conn, fid, af_id, best, verbose=verbose)
        n_markets_rows += rows_written
        conn.commit()
        if "BTTS" in best:
            bkm, _ = best["BTTS"]
            parts.append(f"BTTS ({bkm})")
        if "OVER_UNDER" in best:
            bkm, _ = best["OVER_UNDER"]
            parts.append(f"O/U ({bkm})")

        status = "[NEW]  " if not already_1x2 else "[MKT]  "
        if verbose:
            print(f"  {status}{label:<46}  {' | '.join(parts)}")

    # Commit any pending writes
    conn.close()

    summary = {
        "n_total":        n_total,
        "n_no_af_link":   n_no_af_link,
        "n_skipped":      n_skipped,
        "n_1x2_filled":   n_1x2_filled,
        "n_markets_rows": n_markets_rows,
        "n_no_data":      n_no_data,
        "n_failed":       n_failed,
    }
    return summary


# ── Post-sync validation report ──────────────────────────────────────────────

def report_market_coverage(week: int, year: int) -> None:
    """
    Print odds coverage for the active coupon:
        BTTS: X/12  |  Over 2.5: X/12  |  Under 2.5: X/12  |  1X2: X/12
    """
    from db.connection import get_conn
    from db.coupon import list_coupons, get_coupon_matches

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        print(f"  No coupons for week {week}/{year}")
        return

    all_fids: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            fid = m["fixture_id"]
            if fid not in seen:
                seen.add(fid)
                all_fids.append((fid, m.get("home_name", "?"), m.get("away_name", "?")))

    n = len(all_fids)
    with get_conn() as conn:
        def _count_market(mkt: str, sel: str | None = None) -> int:
            if sel:
                q = "SELECT COUNT(DISTINCT fixture_id) FROM odds_markets WHERE fixture_id IN ({}) AND market_key=? AND selection=?".format(
                    ",".join("?" * n))
                return conn.execute(q, [f[0] for f in all_fids] + [mkt, sel]).fetchone()[0]
            else:
                q = "SELECT COUNT(DISTINCT fixture_id) FROM odds_markets WHERE fixture_id IN ({}) AND market_key=?".format(
                    ",".join("?" * n))
                return conn.execute(q, [f[0] for f in all_fids] + [mkt]).fetchone()[0]

        def _count_1x2() -> int:
            q = "SELECT COUNT(DISTINCT fixture_id) FROM odds WHERE fixture_id IN ({})".format(
                ",".join("?" * n))
            return conn.execute(q, [f[0] for f in all_fids]).fetchone()[0]

        n_1x2   = _count_1x2()
        n_btts  = _count_market("BTTS")
        n_over  = _count_market("OVER_UNDER", "OVER")
        n_under = _count_market("OVER_UNDER", "UNDER")

    sep = "-" * 50
    print(f"\n  Market odds coverage (week {week}/{year}) {sep[:20]}")
    print(f"  1X2 odds:      {n_1x2:2d} / {n}")
    print(f"  BTTS odds:     {n_btts:2d} / {n}")
    print(f"  Over 2.5:      {n_over:2d} / {n}")
    print(f"  Under 2.5:     {n_under:2d} / {n}")

    with get_conn() as chk:
        missing_btts = [f"{h} vs {a}" for fid, h, a in all_fids
                        if not _has_market_inline(chk, fid, "BTTS")]
        missing_over = [f"{h} vs {a}" for fid, h, a in all_fids
                        if not _has_market_inline(chk, fid, "OVER_UNDER")]
    if missing_btts:
        print(f"\n  Missing BTTS odds ({len(missing_btts)}):")
        for m in missing_btts:
            print(f"    - {m}")
    if missing_over:
        print(f"\n  Missing Over/Under odds ({len(missing_over)}):")
        for m in missing_over:
            print(f"    - {m}")
    print()


def _has_market_inline(conn, fixture_id: str, market_key: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM odds_markets WHERE fixture_id=? AND market_key=? LIMIT 1",
        (fixture_id, market_key),
    ).fetchone() is not None


# ── Leagues to scan for global Modellspill odds intelligence ─────────────────
# (league_id, season) pairs — all with valid AF fixture + odds coverage.
# Ordered: NT-relevant first, then major European leagues by betting volume.
_SCAN_LEAGUES: list[tuple[int, int]] = [
    # NT-relevant Norwegian domestic + international
    (103, 2026),   # Eliteserien
    (104, 2026),   # OBOS-ligaen
    (725, 2026),   # Toppserien
    (1,   2026),   # FIFA World Cup
    (2,   2026),   # UEFA Champions League
    (5,   2025),   # UEFA Nations League (A)
    # Major European top divisions — highest odds liquidity
    # season=2025 → 2025/26 season (Aug 2025–May 2026); active during regular season
    (39,  2025),   # Premier League (England)
    (40,  2025),   # Championship (England)
    (41,  2025),   # League One (England)
    (42,  2025),   # League Two (England)
    (140, 2025),   # La Liga (Spain)
    (135, 2025),   # Serie A (Italy)
    (78,  2025),   # Bundesliga (Germany)
    (79,  2025),   # 2. Bundesliga (Germany)
    (61,  2025),   # Ligue 1 (France)
    (88,  2025),   # Eredivisie (Netherlands)
    (94,  2025),   # Primeira Liga (Portugal)
    (179, 2025),   # Scottish Premiership
    (119, 2025),   # Danish Superliga
    (169, 2025),   # Belgian Pro League
    # Nordic + smaller European
    (113, 2026),   # Allsvenskan (Sweden)
    (114, 2026),   # Superettan (Sweden)
    (164, 2026),   # Úrvalsdeild (Iceland)
    (244, 2026),   # Veikkausliiga (Finland)
    (357, 2026),   # IRL Premier Division
    (358, 2026),   # IRL First Division
    (72,  2026),   # BRA Série B
]


def scan_af_market_odds(
    lookahead_hours: int = 72,
    verbose: bool = False,
) -> dict:
    """
    Global odds intelligence scan — NOT limited to NT coupon fixtures.

    For each tracked league, fetches upcoming fixtures within the lookahead
    window and stores odds in `odds` + `odds_markets`. New fixtures that are
    not yet in the DB are inserted into `fixtures` + `api_football_fixture_links`
    so the model evaluation pipeline can later operate on them.

    Idempotent: safe to call repeatedly. BTTS/O/U always upserted; 1X2 skipped
    if already present. New fixture rows are inserted with INSERT OR IGNORE.

    Returns a summary dict with counts of fixtures scanned, odds stored, etc.
    """
    from db.connection import get_conn
    from config import API_FOOTBALL_KEY
    from ingestion.api_football import get_fixtures

    if not API_FOOTBALL_KEY:
        return {"error": "API_FOOTBALL_KEY not set", "n_leagues": 0}

    now_utc    = datetime.now(timezone.utc)
    from_date  = now_utc.strftime("%Y-%m-%d")
    to_dt      = now_utc + timedelta(hours=lookahead_hours)
    to_date    = to_dt.strftime("%Y-%m-%d")

    n_leagues_scanned = 0
    n_fixtures_found  = 0
    n_fixtures_new    = 0
    n_1x2_stored      = 0
    n_markets_stored  = 0
    n_no_odds         = 0
    n_errors          = 0
    n_calls           = 0

    conn = get_conn()

    def _fixture_by_af_id(af_id: int) -> str | None:
        row = conn.execute(
            "SELECT fixture_id FROM api_football_fixture_links WHERE api_football_fixture_id=?",
            (af_id,),
        ).fetchone()
        return row[0] if row else None

    def _has_1x2(fid: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM odds WHERE fixture_id=?", (fid,)
        ).fetchone() is not None

    def _upsert_fixture(af_fix: dict, league_id: int, season: int) -> str:
        """Insert fixture + AF link if not present. Returns fixture_id."""
        af_id     = af_fix["fixture"]["id"]
        kickoff   = af_fix["fixture"].get("date", "")
        home_name = af_fix["teams"]["home"]["name"]
        away_name = af_fix["teams"]["away"]["name"]
        home_af   = af_fix["teams"]["home"]["id"]
        away_af   = af_fix["teams"]["away"]["id"]

        fid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO fixtures (fixture_id, kickoff_utc, external_id, home_name, away_name, created_at)
               VALUES (?,?,?,?,?,datetime('now'))
               ON CONFLICT(external_id) DO UPDATE SET home_name=excluded.home_name, away_name=excluded.away_name""",
            (fid, kickoff, af_id, home_name, away_name),
        )
        # Resolve the actual fixture_id (may be pre-existing row)
        existing = conn.execute(
            "SELECT fixture_id FROM fixtures WHERE external_id=?", (af_id,)
        ).fetchone()
        real_fid = existing[0] if existing else fid

        conn.execute(
            """INSERT OR IGNORE INTO api_football_fixture_links
               (fixture_id, api_football_fixture_id, api_football_league_id,
                api_football_season, api_football_home_team_id,
                api_football_away_team_id, match_confidence)
               VALUES (?,?,?,?,?,?,1.0)""",
            (real_fid, af_id, league_id, season, home_af, away_af),
        )
        conn.commit()
        return real_fid

    for league_id, season in _SCAN_LEAGUES:
        if n_calls > 0:
            time.sleep(_DELAY)
        n_calls += 1
        n_leagues_scanned += 1

        try:
            fixtures = get_fixtures(
                league_id=league_id,
                season=season,
                from_date=from_date,
                to_date=to_date,
            )
        except Exception as exc:
            if verbose:
                print(f"  [ERR]  league {league_id} fixture fetch: {exc}")
            n_errors += 1
            continue

        for af_fix in fixtures:
            af_id = af_fix.get("fixture", {}).get("id")
            if not af_id:
                continue

            # Only upcoming/live (not finished)
            status = af_fix.get("fixture", {}).get("status", {}).get("short", "")
            if status in ("FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "INT"):
                continue

            n_fixtures_found += 1
            home_name = af_fix["teams"]["home"]["name"]
            away_name = af_fix["teams"]["away"]["name"]
            label     = f"{home_name} vs {away_name}"

            # Resolve or create fixture in DB
            existing_fid = _fixture_by_af_id(af_id)
            if existing_fid:
                fid = existing_fid
            else:
                fid = _upsert_fixture(af_fix, league_id, season)
                n_fixtures_new += 1
                if verbose:
                    print(f"  [NEW-FIX] {label} (af={af_id}, fid={fid[:8]})")

            already_1x2  = _has_1x2(fid)
            already_btts = _has_market_inline(conn, fid, "BTTS")
            already_ou   = _has_market_inline(conn, fid, "OVER_UNDER")

            if already_1x2 and already_btts and already_ou:
                if verbose:
                    print(f"  [DONE]  {label}")
                continue

            time.sleep(_DELAY)
            n_calls += 1

            try:
                best = fetch_af_all_markets(af_id)
            except Exception as exc:
                if verbose:
                    print(f"  [ERR]   {label}: {exc}")
                n_errors += 1
                continue

            if not best:
                if verbose:
                    print(f"  [NONE]  {label} (no odds)")
                n_no_odds += 1
                continue

            parts: list[str] = []

            if not already_1x2 and "1X2" in best:
                bkm, rows = best["1X2"]
                sel_map = {r["selection"]: r["odds"] for r in rows}
                try:
                    h = sel_map["HOME"]
                    u = sel_map["DRAW"]
                    b = sel_map["AWAY"]
                    conn.execute(
                        "INSERT INTO odds (fixture_id, source, odds_h, odds_u, odds_b) VALUES (?,?,?,?,?)",
                        (fid, f"api_football:{bkm}", h, u, b),
                    )
                    conn.commit()
                    n_1x2_stored += 1
                    parts.append(f"1X2 ({bkm})")
                except KeyError:
                    pass
            elif already_1x2:
                parts.append("1X2 ✓")

            mkt_n = _store_market_odds(conn, fid, af_id, best, verbose=False)
            conn.commit()
            n_markets_stored += mkt_n
            if "BTTS" in best:
                parts.append(f"BTTS")
            if "OVER_UNDER" in best:
                parts.append(f"O/U")

            if verbose and parts:
                print(f"  [OK]    {label:<50} {' | '.join(parts)}")

    # ── Phase 2: fetch AF Predictions for fixtures missing them ─────────────────
    # Only fetches fixtures that have an AF link but no prediction stored yet.
    # This enables the model quality hierarchy in generate_global_bet_candidates.
    n_preds_stored = 0
    n_preds_failed = 0
    try:
        from ingestion.api_football_predictions import (
            fetch_af_prediction, parse_prediction, store_prediction,
        )
        now_utc = _now_utc()
        unpredicted = conn.execute(
            """SELECT DISTINCT lnk.fixture_id, lnk.api_football_fixture_id
               FROM api_football_fixture_links lnk
               JOIN fixtures f ON f.fixture_id = lnk.fixture_id
               LEFT JOIN api_football_predictions p ON p.fixture_id = lnk.fixture_id
               WHERE f.kickoff_utc > ? AND p.fixture_id IS NULL""",
            (now_utc,),
        ).fetchall()

        for row in unpredicted:
            fid   = row["fixture_id"]
            af_id = row["api_football_fixture_id"]
            time.sleep(_DELAY)
            n_calls += 1
            raw = fetch_af_prediction(af_id)
            if raw is None:
                n_preds_failed += 1
                continue
            try:
                parsed = parse_prediction(raw)
                store_prediction(conn, fid, af_id, parsed)
                conn.commit()
                n_preds_stored += 1
            except Exception:
                n_preds_failed += 1
    except Exception:
        pass

    conn.close()

    return {
        "lookahead_hours":  lookahead_hours,
        "n_leagues":        n_leagues_scanned,
        "n_fixtures_found": n_fixtures_found,
        "n_fixtures_new":   n_fixtures_new,
        "n_1x2_stored":     n_1x2_stored,
        "n_markets_stored": n_markets_stored,
        "n_no_odds":        n_no_odds,
        "n_errors":         n_errors,
        "n_api_calls":      n_calls,
        "n_preds_stored":   n_preds_stored,
        "scanned_at":       _now_utc(),
    }
