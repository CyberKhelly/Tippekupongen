"""
API-Football predictions ingestion.

Fetches GET /predictions?fixture={af_fixture_id} for all NT coupon fixtures.

Key signals extracted:
  - winner.name / winner.comment — directional prediction
  - win_or_draw                  — double chance flag
  - under_over                   — sign indicates Over(+) / Under(-)
  - advice                       — text explanation
  - comparison.poisson_distribution — relative home/away strength (best numeric signal)
  - comparison.goals             — goal scoring strength comparison

Note: percent.home/draw/away are often defaulted (45%/45%/10% on WC fixtures) —
do not use them as primary signals. Use poisson_distribution + winner instead.

Usage:
    from ingestion.api_football_predictions import scan_nt_predictions
    summary = scan_nt_predictions(week=26, year=2026)
"""
from __future__ import annotations

import json
import time
import unicodedata
from datetime import datetime, timezone

from ingestion.api_football_odds import _get_json, _DELAY

# --- Name normalisation ----------------------------------------------------------

def _normalise(name: str) -> str:
    """Lowercase, strip diacritics, strip common club suffixes."""
    nfkd = unicodedata.normalize("NFKD", name.lower())
    ascii_name = "".join(c for c in nfkd if not unicodedata.combining(c))
    for suffix in (" fc", " if", " bk", " fk", " sk", " ik", " ff", " aik",
                   " utd", " united", " city", " sc", " ac"):
        if ascii_name.endswith(suffix):
            ascii_name = ascii_name[: -len(suffix)]
    return ascii_name.strip()


def _names_match(a: str, b: str) -> bool:
    na, nb = _normalise(a), _normalise(b)
    return na == nb or na in nb or nb in na


# --- API fetching ---------------------------------------------------------------

def fetch_af_prediction(af_fixture_id: int) -> dict | None:
    """
    Call AF /predictions for one fixture.
    Returns the raw response[0] dict or None.
    """
    try:
        data = _get_json("predictions", {"fixture": af_fixture_id})
    except Exception:
        return None
    errors = data.get("errors", {})
    if errors and errors not in ({}, []):
        return None
    resp = data.get("response", [])
    return resp[0] if resp else None


def parse_prediction(raw: dict) -> dict:
    """
    Extract normalised fields from a single AF /predictions response[0] object.

    Returns a flat dict ready for DB insertion.
    """
    preds = raw.get("predictions", {})
    winner = preds.get("winner") or {}
    goals  = preds.get("goals") or {}
    pct    = preds.get("percent") or {}
    comp   = raw.get("comparison") or {}

    under_over_raw = preds.get("under_over")
    # under_over is a string like "-3.5" or "3.5" — convert to float
    under_over: float | None = None
    if under_over_raw not in (None, "", "null"):
        try:
            under_over = float(str(under_over_raw))
        except (ValueError, TypeError):
            pass

    goals_home_raw = goals.get("home")
    goals_away_raw = goals.get("away")
    goals_home: float | None = None
    goals_away: float | None = None
    if goals_home_raw not in (None, ""):
        try:
            goals_home = float(str(goals_home_raw))
        except (ValueError, TypeError):
            pass
    if goals_away_raw not in (None, ""):
        try:
            goals_away = float(str(goals_away_raw))
        except (ValueError, TypeError):
            pass

    return {
        "prediction_winner_id":      winner.get("id"),
        "prediction_winner_name":    winner.get("name"),
        "prediction_winner_comment": winner.get("comment"),
        "prediction_win_or_draw":    1 if preds.get("win_or_draw") else 0,
        "prediction_under_over":     str(under_over) if under_over is not None else None,
        "prediction_goals_home":     goals_home,
        "prediction_goals_away":     goals_away,
        "advice":                    preds.get("advice"),
        "percent_home":              pct.get("home"),
        "percent_draw":              pct.get("draw"),
        "percent_away":              pct.get("away"),
        "comparison_json":           json.dumps(comp),
        "raw_json":                  json.dumps(raw),
    }


def store_prediction(conn, fixture_id: str, af_fixture_id: int, parsed: dict) -> None:
    """Upsert one prediction row (latest wins on UNIQUE(fixture_id))."""
    conn.execute(
        """INSERT INTO api_football_predictions
           (fixture_id, af_fixture_id,
            prediction_winner_id, prediction_winner_name, prediction_winner_comment,
            prediction_win_or_draw, prediction_under_over,
            prediction_goals_home, prediction_goals_away,
            advice, percent_home, percent_draw, percent_away,
            comparison_json, raw_json, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(fixture_id) DO UPDATE SET
               af_fixture_id               = excluded.af_fixture_id,
               prediction_winner_id        = excluded.prediction_winner_id,
               prediction_winner_name      = excluded.prediction_winner_name,
               prediction_winner_comment   = excluded.prediction_winner_comment,
               prediction_win_or_draw      = excluded.prediction_win_or_draw,
               prediction_under_over       = excluded.prediction_under_over,
               prediction_goals_home       = excluded.prediction_goals_home,
               prediction_goals_away       = excluded.prediction_goals_away,
               advice                      = excluded.advice,
               percent_home                = excluded.percent_home,
               percent_draw                = excluded.percent_draw,
               percent_away                = excluded.percent_away,
               comparison_json             = excluded.comparison_json,
               raw_json                    = excluded.raw_json,
               fetched_at                  = excluded.fetched_at""",
        (
            fixture_id, af_fixture_id,
            parsed["prediction_winner_id"], parsed["prediction_winner_name"],
            parsed["prediction_winner_comment"], parsed["prediction_win_or_draw"],
            parsed["prediction_under_over"], parsed["prediction_goals_home"],
            parsed["prediction_goals_away"], parsed["advice"],
            parsed["percent_home"], parsed["percent_draw"], parsed["percent_away"],
            parsed["comparison_json"], parsed["raw_json"],
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ),
    )


# --- Re-mapping: search AF for fixtures not yet in api_football_fixture_links ---

# Known league IDs for common NT competitions (extend as needed)
_LEAGUE_SEARCH_ORDER = [
    1,    # FIFA World Cup
    104,  # Norwegian OBOS-ligaen (2. div)
    105,  # Norwegian 1. divisjon
    113,  # Swedish Allsvenskan
    114,  # Swedish Superettan
    164,  # Icelandic Úrvalsdeild
    244,  # Finnish Ykkönen
    245,  # Finnish Veikkausliiga
    280,  # Faroese Faroe Islands Premier League
    326,  # Estonian Meistriliiga
    357,  # League of Ireland Premier Division
    72,   # Brazilian Série B
    73,   # Brazilian Série A
]


def try_remap_unmapped(conn, week: int, year: int, verbose: bool = True) -> int:
    """
    Attempt to find AF fixture IDs for NT fixtures not yet in api_football_fixture_links.

    Strategy:
    1. Get all unmapped fixtures for this week.
    2. Determine which AF league IDs to search (from already-mapped fixtures + _LEAGUE_SEARCH_ORDER).
    3. For each unmapped fixture, search AF /fixtures?league=X&season=Y&from=date&to=date.
    4. Match by home + away team name similarity.
    5. If confident match found, insert into api_football_fixture_links.

    Returns number of new links created.
    """
    from db.enrichment import upsert_fixture_link

    unmapped = conn.execute(
        """SELECT DISTINCT f.fixture_id, f.kickoff_utc,
                  th.name_canonical AS home_en,
                  COALESCE(th.name_local, th.name_canonical) AS home_local,
                  ta.name_canonical AS away_en,
                  COALESCE(ta.name_local, ta.name_canonical) AS away_local
           FROM coupon_fixtures cf
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           JOIN fixtures f ON f.fixture_id = cf.fixture_id
           JOIN teams th ON th.team_id = f.home_team_id
           JOIN teams ta ON ta.team_id = f.away_team_id
           LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = f.fixture_id
           WHERE c.week = ? AND c.year = ? AND lnk.api_football_fixture_id IS NULL
           ORDER BY f.kickoff_utc""",
        (week, year),
    ).fetchall()

    if not unmapped:
        return 0

    # Build set of league IDs already known for this week
    known_leagues = set(
        r[0]
        for r in conn.execute(
            """SELECT DISTINCT lnk.api_football_league_id
               FROM api_football_fixture_links lnk
               JOIN coupon_fixtures cf ON cf.fixture_id = lnk.fixture_id
               JOIN coupons c ON c.coupon_id = cf.coupon_id
               WHERE c.week = ? AND c.year = ?""",
            (week, year),
        ).fetchall()
        if r[0]
    )
    leagues_to_try = list(known_leagues) + [
        l for l in _LEAGUE_SEARCH_ORDER if l not in known_leagues
    ]

    # Group unmapped by date for efficient API batching
    from collections import defaultdict
    by_date: dict[str, list] = defaultdict(list)
    for row in unmapped:
        date = row["kickoff_utc"][:10]
        by_date[date].append(row)

    # Cache AF search results: (league_id, date) → list of AF fixture dicts
    search_cache: dict[tuple, list] = {}
    n_calls = 0
    n_new   = 0

    for date, fixtures in sorted(by_date.items()):
        for league_id in leagues_to_try:
            cache_key = (league_id, date)
            if cache_key not in search_cache:
                if n_calls > 0:
                    time.sleep(_DELAY)
                n_calls += 1
                try:
                    data = _get_json("fixtures", {
                        "league":  league_id,
                        "season":  year,
                        "from":    date,
                        "to":      date,
                    })
                    search_cache[cache_key] = data.get("response", [])
                except Exception:
                    search_cache[cache_key] = []

        for frow in fixtures:
            # Skip WC bracket placeholders (W73 etc.)
            home_en = frow["home_en"] or ""
            away_en = frow["away_en"] or ""
            if (home_en.startswith("W") and home_en[1:].isdigit()) or \
               (away_en.startswith("W") and away_en[1:].isdigit()):
                if verbose:
                    print(f"  [SKIP]  {home_en} vs {away_en} (bracket placeholder)")
                continue

            date = frow["kickoff_utc"][:10]
            found: dict | None = None

            for league_id in leagues_to_try:
                for af_fix in search_cache.get((league_id, date), []):
                    af_home = af_fix.get("teams", {}).get("home", {}).get("name", "")
                    af_away = af_fix.get("teams", {}).get("away", {}).get("name", "")
                    home_match = (
                        _names_match(home_en, af_home) or
                        _names_match(frow["home_local"], af_home)
                    )
                    away_match = (
                        _names_match(away_en, af_away) or
                        _names_match(frow["away_local"], af_away)
                    )
                    if home_match and away_match:
                        found = {
                            "af_fixture_id":   af_fix["fixture"]["id"],
                            "af_league_id":    league_id,
                            "af_home_team_id": af_fix["teams"]["home"]["id"],
                            "af_away_team_id": af_fix["teams"]["away"]["id"],
                        }
                        break
                if found:
                    break

            if found:
                upsert_fixture_link(
                    fixture_id=frow["fixture_id"],
                    af_fixture_id=found["af_fixture_id"],
                    af_league_id=found["af_league_id"],
                    af_season=year,
                    af_home_team_id=found["af_home_team_id"],
                    af_away_team_id=found["af_away_team_id"],
                    match_confidence=0.85,
                )
                n_new += 1
                if verbose:
                    print(f"  [MAP]   {home_en} vs {away_en} -> AF {found['af_fixture_id']} (league {found['af_league_id']})")
            else:
                if verbose:
                    print(f"  [MISS]  {home_en} vs {away_en} (not found in AF)")

    return n_new


# --- Main scanner ---------------------------------------------------------------

def scan_nt_predictions(
    week: int,
    year: int,
    verbose: bool = True,
    remap: bool = True,
) -> dict:
    """
    Full NT prediction scanner:
    1. Optionally re-map unmapped fixtures.
    2. Fetch AF /predictions for all fixtures with AF links.
    3. Store in api_football_predictions table.
    4. Return summary + top signals.

    Returns:
        n_total           — total NT fixtures
        n_mapped          — fixtures with AF link
        n_unmapped        — no AF link
        n_fetched         — predictions successfully fetched
        n_no_data         — AF returned no prediction
        n_failed          — API errors
        n_new_links       — new AF links created by remapper
        top_signals       — list of top prediction dicts (sorted by confidence)
    """
    from db.connection import get_conn
    from db.schema import init_db
    from db.coupon import list_coupons, get_coupon_matches

    init_db()
    conn = get_conn()

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Deduplicate fixtures
    seen: set[str] = set()
    all_fixtures: list[dict] = []
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            fid = m["fixture_id"]
            if fid not in seen:
                seen.add(fid)
                all_fixtures.append(m)

    n_total = len(all_fixtures)

    # Step 1: re-map
    n_new_links = 0
    if remap:
        if verbose:
            print(f"\n  Attempting to map unmapped fixtures...")
        n_new_links = try_remap_unmapped(conn, week=week, year=year, verbose=verbose)
        if verbose:
            print(f"  New links created: {n_new_links}\n")

    # Step 2: fetch predictions for all fixtures with AF links
    def _af_link(fixture_id: str) -> tuple[int | None, int | None]:
        row = conn.execute(
            """SELECT api_football_fixture_id, api_football_home_team_id
               FROM api_football_fixture_links WHERE fixture_id=?""",
            (fixture_id,),
        ).fetchone()
        return (row[0], row[1]) if row else (None, None)

    n_mapped = n_unmapped = n_fetched = n_no_data = n_failed = 0
    n_calls = 0
    top_signals: list[dict] = []

    for m in all_fixtures:
        fid  = m["fixture_id"]
        home = m.get("home_name", "?")
        away = m.get("away_name", "?")

        af_id, af_home_team_id = _af_link(fid)
        if af_id is None:
            n_unmapped += 1
            if verbose:
                print(f"  [UNMAPPED]  {home} vs {away}")
            continue

        n_mapped += 1

        if n_calls > 0:
            time.sleep(_DELAY)
        n_calls += 1

        raw = fetch_af_prediction(af_id)
        if raw is None:
            n_no_data += 1
            if verbose:
                print(f"  [NO DATA]   {home} vs {away}  (af_id={af_id})")
            continue

        try:
            parsed = parse_prediction(raw)
            store_prediction(conn, fid, af_id, parsed)
            conn.commit()
            n_fetched += 1

            winner = parsed.get("prediction_winner_name") or "?"
            advice = parsed.get("advice") or "—"
            uo     = parsed.get("prediction_under_over")
            if verbose:
                uo_str = f"  O/U={uo}" if uo else ""
                print(f"  [OK]        {home} vs {away}  -> {winner}  [{advice}]{uo_str}")

            top_signals.append({
                "fixture_id": fid,
                "home":       home,
                "away":       away,
                "af_id":      af_id,
                **parsed,
            })
        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f"  [ERR]       {home} vs {away}  {exc}")

    conn.close()

    return {
        "n_total":     n_total,
        "n_mapped":    n_mapped,
        "n_unmapped":  n_unmapped,
        "n_fetched":   n_fetched,
        "n_no_data":   n_no_data,
        "n_failed":    n_failed,
        "n_new_links": n_new_links,
        "top_signals": top_signals,
    }


# --- Confidence scoring ---------------------------------------------------------

def compute_confidence_score(
    market_edge_pp: float | None,
    af_agrees: bool | None,
    af_has_data: bool,
    odds_movement_direction: str | None,
    has_bookmaker_odds: bool,
    has_odds_movement: bool,
    af_poisson_home_pct: float | None = None,
    is_home_pick: bool = False,
) -> float:
    """
    Returns 0–100 confidence score.

    Weights:
      model edge:            40%
      AF agreement:          25%
      odds movement:         15%
      prediction confidence: 10%
      data quality:          10%
    """
    # ── Model edge (0–40) ────────────────────────────────────────────────────
    edge   = market_edge_pp or 0.0
    edge_s = min(40.0, max(0.0, edge * 2.0))   # 5pp→10, 10pp→20, 20pp→40

    # ── AF agreement (0–25) ─────────────────────────────────────────────────
    if af_has_data:
        if af_agrees is True:
            af_s = 25.0
        elif af_agrees is False:
            af_s = 0.0
        else:
            af_s = 10.0   # neutral / unknown
    else:
        af_s = 5.0        # no AF data

    # ── Odds movement (0–15) ─────────────────────────────────────────────────
    if has_odds_movement:
        if odds_movement_direction == "steaming":
            mv_s = 15.0
        elif odds_movement_direction == "stable":
            mv_s = 10.0
        else:  # drifting
            mv_s = 3.0
    else:
        mv_s = 7.0  # neutral when no data

    # ── Prediction confidence (0–10) ─────────────────────────────────────────
    # Use AF poisson distribution divergence from 50% as signal strength
    if af_has_data and af_poisson_home_pct is not None:
        divergence = abs(af_poisson_home_pct - 50.0)
        pred_s = min(10.0, divergence / 5.0)   # 75% vs 25% → 10 pts
    elif af_has_data:
        pred_s = 5.0
    else:
        pred_s = 2.0

    # ── Data quality (0–10) ──────────────────────────────────────────────────
    dq_s = (5.0 if has_bookmaker_odds else 0.0) + \
           (3.0 if af_has_data else 0.0) + \
           (2.0 if has_odds_movement else 0.0)

    return round(edge_s + af_s + mv_s + pred_s + dq_s, 1)
