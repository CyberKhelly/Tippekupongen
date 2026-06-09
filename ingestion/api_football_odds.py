"""
API-Football odds ingestion — fallback for fixtures with no existing odds.

Inserts odds ONLY when a fixture has no odds row at all.
Never overwrites Pinnacle, norsk_tipping, manual, or any other existing source.

Bookmaker selection priority (first found in response):
    Bet365 → William Hill → Marathonbet → 10Bet → first available

Usage:
    from ingestion.api_football_odds import ingest_af_odds_fallback
    summary = ingest_af_odds_fallback(week=24, year=2026)
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

from config import API_FOOTBALL_KEY

_BASE = "https://v3.football.api-sports.io"
_DELAY = 2.1          # seconds between requests (AF limit: 30/min)
_TIMEOUT = 15         # socket timeout seconds

# Bookmakers in preferred priority order (AF canonical names)
_PREFERRED = ["Bet365", "William Hill", "Marathonbet", "10Bet"]


def _get_json(path: str, params: dict) -> dict:
    if not API_FOOTBALL_KEY:
        raise EnvironmentError("API_FOOTBALL_KEY not set")
    qs  = urllib.parse.urlencode(params)
    url = f"{_BASE}/{path}?{qs}"
    req = urllib.request.Request(url, headers={"x-apisports-key": API_FOOTBALL_KEY})
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
        return json.loads(resp.read())


def fetch_af_1x2(af_fixture_id: int) -> tuple[float, float, float, str] | None:
    """
    Call /odds for one AF fixture. Returns (odds_h, odds_u, odds_b, bookmaker) or None.

    Picks the highest-priority bookmaker that offers a Match Winner / 1X2 market.
    """
    try:
        data = _get_json("odds", {"fixture": af_fixture_id})
    except Exception:
        return None

    errors = data.get("errors", {})
    if errors and errors not in ({}, []):
        return None

    items = data.get("response", [])
    if not items:
        return None

    # Collect all bookmakers across response items
    all_bookmakers: dict[str, tuple[float, float, float]] = {}
    for item in items:
        for bookie in item.get("bookmakers", []):
            bname = bookie.get("name", "")
            if not bname or bname in all_bookmakers:
                continue
            for bet in bookie.get("bets", []):
                if bet.get("name") in ("Match Winner", "1X2"):
                    vals = {v["value"]: v["odd"] for v in bet.get("values", [])}
                    try:
                        h = float(vals["Home"])
                        u = float(vals["Draw"])
                        b = float(vals["Away"])
                        if h > 1.0 and u > 1.0 and b > 1.0:
                            all_bookmakers[bname] = (h, u, b)
                    except (KeyError, ValueError):
                        pass
                    break

    if not all_bookmakers:
        return None

    # Return preferred bookmaker, or first available
    for preferred in _PREFERRED:
        if preferred in all_bookmakers:
            h, u, b = all_bookmakers[preferred]
            return h, u, b, preferred

    bname, (h, u, b) = next(iter(all_bookmakers.items()))
    return h, u, b, bname


def ingest_af_odds_fallback(
    week: int,
    year: int,
    verbose: bool = True,
) -> dict:
    """
    For all active NT fixtures in the given week that have an AF link but no odds:
    - skip fixtures that already have ANY odds row (any source)
    - skip fixtures with no api_football_fixture_links entry
    - call AF /odds for each remaining fixture
    - insert with source='api_football' using upsert_odds()

    Returns a summary dict:
        n_total        — total fixtures checked
        n_already_have — already had odds (skipped)
        n_no_af_link   — no AF fixture match (skipped)
        n_filled       — new odds inserted
        n_no_odds_data — AF returned no odds
        n_failed       — API errors
    """
    from db.connection import get_conn
    from db.coupon import list_coupons, get_coupon_matches, upsert_odds

    if not API_FOOTBALL_KEY:
        if verbose:
            print("  AF odds: API_FOOTBALL_KEY not set — skipping.")
        return {"n_total": 0, "n_already_have": 0, "n_no_af_link": 0,
                "n_filled": 0, "n_no_odds_data": 0, "n_failed": 0}

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Collect all fixtures for the week (deduplicated by fixture_id)
    seen: set[str] = set()
    all_fixtures: list[dict] = []
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            fid = m["fixture_id"]
            if fid not in seen:
                seen.add(fid)
                all_fixtures.append(m)

    conn = get_conn()

    def _has_odds(fixture_id: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM odds WHERE fixture_id = ?", (fixture_id,)
        ).fetchone() is not None

    def _af_link(fixture_id: str) -> int | None:
        row = conn.execute(
            "SELECT api_football_fixture_id FROM api_football_fixture_links WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
        return row[0] if row else None

    n_total = len(all_fixtures)
    n_already_have = n_no_af_link = n_filled = n_no_odds_data = n_failed = 0
    n_calls = 0  # counts actual AF /odds calls, drives the rate-limit delay

    for m in all_fixtures:
        fid   = m["fixture_id"]
        home  = m.get("home_name", "?")
        away  = m.get("away_name", "?")
        label = f"{home} vs {away}"

        # Skip if odds already exist
        if _has_odds(fid):
            n_already_have += 1
            if verbose:
                print(f"  [SKIP] {label:<44}  (has odds)")
            continue

        # Skip if no AF link
        af_id = _af_link(fid)
        if af_id is None:
            n_no_af_link += 1
            if verbose:
                print(f"  [SKIP] {label:<44}  (no AF link)")
            continue

        # Rate-limit pause only before actual API calls (not the first one)
        if n_calls > 0:
            time.sleep(_DELAY)
        n_calls += 1

        # Fetch odds from AF
        try:
            result = fetch_af_1x2(af_id)
        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f"  [ERR]  {label:<44}  {exc}")
            continue

        if result is None:
            n_no_odds_data += 1
            if verbose:
                print(f"  [NONE] {label:<44}  (AF has no 1X2 odds)")
            continue

        h, u, b, bkm = result
        upsert_odds(fid, "api_football", h, u, b)
        n_filled += 1
        if verbose:
            print(
                f"  [OK]   {label:<44}  "
                f"H={h:.2f} U={u:.2f} B={b:.2f}  ({bkm})"
            )

    return {
        "n_total":        n_total,
        "n_already_have": n_already_have,
        "n_no_af_link":   n_no_af_link,
        "n_filled":       n_filled,
        "n_no_odds_data": n_no_odds_data,
        "n_failed":       n_failed,
    }
