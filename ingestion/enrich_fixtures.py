"""
Phase 4B: Statistical Enrichment Layer.

Fetches and stores API-Football context for active NT fixtures.
NT remains source of truth — API-Football only enriches existing fixtures.

Usage:
    from ingestion.enrich_fixtures import enrich_active_fixtures
    summary = enrich_active_fixtures(week=24, year=2026)
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone

import json

from ingestion.api_football import (
    map_nt_competition, translate_team_name, normalize_opponent_name,
    get_fixtures, get_standings, get_team_statistics, get_predictions,
    get_fixture_statistics,
)
# get_predictions is imported for optional reference use only.
# AF predictions must NOT influence H/U/B probabilities or recommendations.
from db.enrichment import upsert_fixture_link, upsert_stat_enrichment
from db.coupon import list_coupons, get_coupon_matches


def _calc_confidence(home_en: str, away_en: str, af_home: str, af_away: str) -> float:
    """Score 0.0–1.0 based on how well the normalized team names agree."""
    def exact(a: str, b: str) -> bool:
        return a == b

    def sub(a: str, b: str) -> bool:
        return len(a) >= 3 and (a in b or b in a)

    h_exact = exact(home_en, af_home)
    a_exact = exact(away_en, af_away)
    h_sub   = sub(home_en, af_home)
    a_sub   = sub(away_en, af_away)

    if h_exact and a_exact: return 1.00
    if h_exact and a_sub:   return 0.90
    if h_sub   and a_exact: return 0.90
    if h_sub   and a_sub:   return 0.80
    return 0.0


def _match_to_af(
    home_name: str, away_name: str, af_fixtures: list[dict]
) -> tuple[dict | None, float]:
    """
    Try to match NT home/away team names to an AF fixture.
    Returns (af_fixture, confidence) — confidence ≥ 0.80 is required.
    """
    home_en = translate_team_name(home_name)
    away_en = translate_team_name(away_name)

    best_match = None
    best_conf  = 0.0

    for af in af_fixtures:
        af_home = translate_team_name(af.get("teams", {}).get("home", {}).get("name", ""))
        af_away = translate_team_name(af.get("teams", {}).get("away", {}).get("name", ""))
        conf = _calc_confidence(home_en, away_en, af_home, af_away)
        if conf > best_conf:
            best_conf  = conf
            best_match = af

    return (best_match, best_conf) if best_conf >= 0.80 else (None, 0.0)


def _parse_pct(s: str | None) -> float | None:
    """Parse '45%' → 0.45."""
    if not s:
        return None
    try:
        return float(str(s).rstrip("%")) / 100
    except (ValueError, AttributeError):
        return None


def _record(wins: int, draws: int, loses: int) -> str:
    return f"W{wins} D{draws} L{loses}"


def _parse_recent_matches(
    fixtures: list[dict],
    team_id:  int,
    n:        int = 5,
    form_str: str | None = None,
) -> list[dict] | None:
    """
    Parse the last N completed AF fixtures for a team into pip-tooltip objects.
    AF returns newest-first; we reverse to oldest-first so index i aligns with
    the i-th character of home_last_5 / away_last_5 (also oldest-first).

    Safety guard: if form_str is supplied, derive the W/D/L sequence from the
    fetched fixtures and compare it to the tail of form_str.  If they do not
    match character-for-character, return None so the frontend falls back to the
    simple "W · Seier" tooltip rather than showing wrong opponent data.
    """
    result = []
    for f in fixtures[:n]:
        fix   = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})

        home_id    = teams.get("home", {}).get("id")
        home_goals = goals.get("home")
        away_goals = goals.get("away")

        is_home = (home_id == team_id)
        opp     = teams.get("away" if is_home else "home", {})

        if home_goals is None or away_goals is None:
            result_char = None
        elif is_home:
            result_char = "W" if home_goals > away_goals else ("D" if home_goals == away_goals else "L")
        else:
            result_char = "W" if away_goals > home_goals else ("D" if home_goals == away_goals else "L")

        score_for     = (home_goals if is_home else away_goals)
        score_against = (away_goals if is_home else home_goals)

        date_str = (fix.get("date") or "")[:10] or None

        result.append({
            "fixture_id":     fix.get("id"),
            "date":           date_str,
            "venue":          "home" if is_home else "away",
            "result":         result_char,
            "score_for":      score_for,
            "score_against":  score_against,
            "opponent_id":    opp.get("id"),
            "opponent_name":  normalize_opponent_name(opp.get("name")),
            "opponent_logo":  opp.get("logo"),
        })

    # Reverse to oldest-first (matches form string ordering)
    result.reverse()

    # ── Alignment validation ──────────────────────────────────────────────────
    # The form string (from team statistics in this league/season) must agree
    # with the W/D/L sequence derived from the fetched fixtures.  A mismatch
    # means the recent fixtures are from a different competition context and
    # we must not display them as tooltip data.
    if form_str:
        derived = "".join(m["result"] or "?" for m in result)
        tail    = form_str.upper()[-len(result):]
        if derived != tail:
            return None

    return result


def _parse_stat_value(val) -> float | None:
    """
    Parse a fixture-statistics value to float.
    Handles:  "59%" → 59.0  |  "1.83" (xG) → 1.83  |  7 (int) → 7.0  |  None → None
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        s = val.strip().rstrip("%")
        try:
            return float(s)
        except ValueError:
            return None
    return None


# Exact stat-type labels as returned by API-Football /fixtures/statistics.
# Do NOT rename — field names are brittle; confirmed against live API 2026-06-21.
_STAT_LABELS = {
    "avg_possession":    "Ball Possession",     # "59%" string — stored without %
    "avg_shots_on_goal": "Shots on Goal",
    "avg_total_shots":   "Total Shots",
    "avg_corners":       "Corner Kicks",
    "avg_fouls":         "Fouls",
    "avg_yellow_cards":  "Yellow Cards",
    "avg_red_cards":     "Red Cards",
    "avg_pass_accuracy": "Passes %",            # "89%" string — stored without %
    "avg_xg":            "expected_goals",      # "1.83" string — available on Pro plan
}


def _extract_stat(stats_list: list[dict], label: str) -> float | None:
    """Extract and parse a single stat from a /fixtures/statistics team block."""
    for item in stats_list:
        if item.get("type") == label:
            return _parse_stat_value(item.get("value"))
    return None


def _aggregate_fixture_stats(
    recent_fixtures: list[dict],
    team_id: int,
    fix_stats_cache: dict,
) -> dict | None:
    """
    For a list of recently completed AF fixtures, fetch /fixtures/statistics for each,
    extract this team's stats, and return an aggregated JSON-serialisable dict.

    Returns None when no stats are available (e.g. OBOS-ligaen, Toppserien).
    Never mixes competitions — recent_fixtures must already be filtered by league+season.
    """
    accumulators: dict[str, list[float]] = {k: [] for k in _STAT_LABELS}
    fixture_ids_used: list[int] = []

    for f in recent_fixtures:
        af_fix_id = f.get("fixture", {}).get("id")
        if af_fix_id is None:
            continue

        # /fixtures/statistics?fixture=X returns both teams — cache per fixture_id
        if af_fix_id not in fix_stats_cache:
            try:
                fix_stats_cache[af_fix_id] = get_fixture_statistics(af_fix_id)
            except Exception:
                fix_stats_cache[af_fix_id] = []

        fix_stats = fix_stats_cache.get(af_fix_id, [])
        if not fix_stats:
            continue

        # Find this team's block
        team_stats: list[dict] = []
        for block in fix_stats:
            if block.get("team", {}).get("id") == team_id:
                team_stats = block.get("statistics", [])
                break

        if not team_stats:
            continue

        # Extract each stat; skip if this fixture has no value for it
        has_any = False
        for key, label in _STAT_LABELS.items():
            val = _extract_stat(team_stats, label)
            if val is not None:
                accumulators[key].append(val)
                has_any = True

        if has_any:
            fixture_ids_used.append(af_fix_id)

    if not fixture_ids_used:
        return None  # no stats available for this competition

    result: dict = {
        "sample_size": len(fixture_ids_used),
        "fixture_ids_used": fixture_ids_used,
    }
    for key in _STAT_LABELS:
        vals = accumulators[key]
        result[key] = round(sum(vals) / len(vals), 2) if vals else None

    return result


def _fetch_enrichment(
    af_fixture_id:    int,
    af_league_id:     int,
    af_season:        int,
    af_home_id:       int,
    af_away_id:       int,
    standings_cache:  dict,
    stats_cache:      dict,
    recent_cache:     dict,
    fix_stats_cache:  dict,
    home_logo_url:    str | None = None,
    away_logo_url:    str | None = None,
    fetch_predictions: bool = False,
) -> dict:
    """
    Fetch standings and team statistics for one matched AF fixture.
    Uses shared caches to avoid redundant API calls across fixtures.

    Phase 10 additions: extracts logos, points, W/D/L, per-match averages,
    clean sheets, streaks, and AF comparison ratings from /predictions.

    AF predictions are stored as reference data only — they do NOT influence
    any H/U/B probabilities or recommendations.
    """
    enrichment: dict = {
        "has_api_football_data":   1,
        "api_football_fixture_id": af_fixture_id,
        "api_football_league_id":  af_league_id,
        "api_football_season":     af_season,
        # Existing fields
        "league_name":  None,
        "home_position": None, "away_position": None,
        "home_form":     None, "away_form":     None,
        "home_last_5":   None, "away_last_5":   None,
        "home_last_10":  None, "away_last_10":  None,
        "home_home_record": None, "away_away_record": None,
        "home_goals_for":  None, "home_goals_against": None,
        "away_goals_for":  None, "away_goals_against": None,
        "api_prediction_home":   None,
        "api_prediction_draw":   None,
        "api_prediction_away":   None,
        "api_prediction_advice": None,
        # Phase 10 — standings
        "home_points":  None, "away_points":  None,
        "home_played":  None, "away_played":  None,
        "home_wins":    None, "home_draws":   None, "home_losses":  None,
        "away_wins":    None, "away_draws":   None, "away_losses":  None,
        # Phase 10 — logos (seed from caller; may be overridden by standings logo)
        "home_logo_url": home_logo_url,
        "away_logo_url": away_logo_url,
        # Phase 10 — per-match averages
        "home_avg_goals_for":     None, "away_avg_goals_for":     None,
        "home_avg_goals_against": None, "away_avg_goals_against": None,
        # Phase 10 — clean sheets and streaks
        "home_clean_sheets":  None, "away_clean_sheets":  None,
        "home_streak_wins":   None, "away_streak_wins":   None,
        "home_streak_draws":  None, "away_streak_draws":  None,
        "home_streak_losses": None, "away_streak_losses": None,
        # Phase 10 — AF comparison ratings (0.0–1.0)
        "api_comparison_att_home":   None, "api_comparison_att_away":   None,
        "api_comparison_def_home":   None, "api_comparison_def_away":   None,
        "api_comparison_form_home":  None, "api_comparison_form_away":  None,
        "api_comparison_total_home": None, "api_comparison_total_away": None,
        # Phase 11 — per-match recent form (JSON strings, null when unavailable)
        "home_recent_matches": None,
        "away_recent_matches": None,
        # Phase 12 — aggregated fixture stats (possession, shots, corners, etc.)
        "home_recent_fixture_stats": None,
        "away_recent_fixture_stats": None,
        # Phase 13 — real league size + venue-specific averages
        "league_size": None,
        "home_avg_goals_for_home":     None,
        "home_avg_goals_against_home": None,
        "away_avg_goals_for_away":     None,
        "away_avg_goals_against_away": None,
        "home_clean_sheets_home": None,
        "away_clean_sheets_away": None,
    }

    # ── Standings ─────────────────────────────────────────────────────────────
    stand_key = (af_league_id, af_season)
    if stand_key not in standings_cache:
        try:
            standings_cache[stand_key] = get_standings(af_league_id, af_season)
        except Exception:
            standings_cache[stand_key] = []

    standings = standings_cache.get(stand_key, [])
    if standings:
        league_info = standings[0].get("league", {})
        enrichment["league_name"] = league_info.get("name")
        groups = league_info.get("standings", [])

        # Build a full team-data map from all groups.
        # First-match-wins: specific group tables (e.g. "Group A") come before
        # aggregate tables (e.g. "Group Stage") in the API response.
        # We use enumerate() for the within-group position (1-based) instead of
        # row["rank"], which for multi-group tournaments is a global/aggregate rank
        # (e.g. Spain at rank 6 from a "Group Stage" combined table).
        team_data: dict[int, dict] = {}
        for group in groups:
            for rank_in_group, row in enumerate(group, 1):
                tid  = row["team"]["id"]
                if tid in team_data:
                    continue  # already captured from their specific group table
                all_ = row.get("all", {})
                team_data[tid] = {
                    "rank":   rank_in_group,
                    "points": row.get("points"),
                    "played": all_.get("played"),
                    "wins":   all_.get("win"),
                    "draws":  all_.get("draw"),
                    "losses": all_.get("lose"),
                    "logo":   row["team"].get("logo"),
                }

        # Phase 13 — real league size from standings.
        # Strategy: find the group that contains the home or away team and use its size.
        # This correctly returns 4 for WC group stage (not the aggregate 48 or 12),
        # and 16 for OBOS-ligaen (single group). Falls back to len(team_data) if not found.
        _home_group_size: int | None = None
        _away_group_size: int | None = None
        for _g in groups:
            _tids = {row["team"]["id"] for row in _g}
            if af_home_id in _tids and _home_group_size is None:
                _home_group_size = len(_g)
            if af_away_id in _tids and _away_group_size is None:
                _away_group_size = len(_g)
        enrichment["league_size"] = _home_group_size or _away_group_size or len(team_data)

        for team_id, prefix in [(af_home_id, "home"), (af_away_id, "away")]:
            td = team_data.get(team_id)
            if not td:
                continue
            enrichment[f"{prefix}_position"] = td["rank"]
            enrichment[f"{prefix}_points"]   = td["points"]
            enrichment[f"{prefix}_played"]   = td["played"]
            enrichment[f"{prefix}_wins"]     = td["wins"]
            enrichment[f"{prefix}_draws"]    = td["draws"]
            enrichment[f"{prefix}_losses"]   = td["losses"]
            # Logo from standings — prefer over caller-supplied fixture logo
            if td.get("logo"):
                enrichment[f"{prefix}_logo_url"] = td["logo"]

    # ── Team statistics ───────────────────────────────────────────────────────
    for team_id, prefix in [(af_home_id, "home"), (af_away_id, "away")]:
        stats_key = (af_league_id, af_season, team_id)
        if stats_key not in stats_cache:
            try:
                stats_cache[stats_key] = get_team_statistics(af_league_id, af_season, team_id)
            except Exception:
                stats_cache[stats_key] = None

        stats = stats_cache.get(stats_key)
        if not stats:
            continue

        # Form strings (existing behaviour)
        form = stats.get("form") or ""
        if form:
            enrichment[f"{prefix}_form"]    = form
            enrichment[f"{prefix}_last_5"]  = form[-5:]  if len(form) >= 5  else form
            enrichment[f"{prefix}_last_10"] = form[-10:] if len(form) >= 10 else form

        # H/A venue-specific record (existing behaviour)
        fix   = stats.get("fixtures", {})
        wins  = fix.get("wins",  {})
        draws = fix.get("draws", {})
        loses = fix.get("loses", {})

        if prefix == "home":
            enrichment["home_home_record"] = _record(
                wins.get("home", 0), draws.get("home", 0), loses.get("home", 0)
            )
        else:
            enrichment["away_away_record"] = _record(
                wins.get("away", 0), draws.get("away", 0), loses.get("away", 0)
            )

        # Season goal totals (existing behaviour)
        goals = stats.get("goals", {})
        gf = goals.get("for",     {}).get("total", {}).get("total") or 0
        ga = goals.get("against", {}).get("total", {}).get("total") or 0
        enrichment[f"{prefix}_goals_for"]     = gf
        enrichment[f"{prefix}_goals_against"] = ga

        # Phase 10 — per-match goal averages
        try:
            gf_avg = goals.get("for",     {}).get("average", {}).get("total")
            ga_avg = goals.get("against", {}).get("average", {}).get("total")
            enrichment[f"{prefix}_avg_goals_for"]     = float(gf_avg) if gf_avg is not None else None
            enrichment[f"{prefix}_avg_goals_against"] = float(ga_avg) if ga_avg is not None else None
        except (TypeError, ValueError):
            pass

        # Phase 10 — clean sheets
        cs = stats.get("clean_sheet", {})
        enrichment[f"{prefix}_clean_sheets"] = cs.get("total")

        # Phase 13 — venue-specific goal averages + clean sheets
        try:
            venue = "home" if prefix == "home" else "away"
            gf_v = goals.get("for",     {}).get("average", {}).get(venue)
            ga_v = goals.get("against", {}).get("average", {}).get(venue)
            enrichment[f"{prefix}_avg_goals_for_{venue}"]     = float(gf_v) if gf_v is not None else None
            enrichment[f"{prefix}_avg_goals_against_{venue}"] = float(ga_v) if ga_v is not None else None
            enrichment[f"{prefix}_clean_sheets_{venue}"]      = cs.get(venue)
        except (TypeError, ValueError):
            pass

        # Phase 10 — current streaks
        biggest = stats.get("biggest", {})
        streak  = biggest.get("streak", {})
        enrichment[f"{prefix}_streak_wins"]   = streak.get("wins")
        enrichment[f"{prefix}_streak_draws"]  = streak.get("draws")
        enrichment[f"{prefix}_streak_losses"] = streak.get("loses")  # AF spells it "loses"

    # ── Recent form matches (Phase 11) ───────────────────────────────────────
    # Fetch last 5 completed fixtures per team IN THIS LEAGUE+SEASON to power
    # pip tooltips.  Filtering by league/season ensures the fetched fixture
    # sequence matches the form string (which is also league/season-specific).
    # Without this filter, national teams would show friendlies/qualifiers that
    # have nothing to do with the WC form string visible in the pip row.
    #
    # Cache key: (team_id, league_id, season) — not just team_id, because the
    # same national team may appear in fixtures from different competitions.
    for team_id, prefix in [(af_home_id, "home"), (af_away_id, "away")]:
        cache_key = (team_id, af_league_id, af_season)
        if cache_key not in recent_cache:
            try:
                recent_cache[cache_key] = get_fixtures(
                    team_id=team_id,
                    league_id=af_league_id,
                    season=af_season,
                    last=5,
                )
            except Exception:
                recent_cache[cache_key] = []
        recent    = recent_cache.get(cache_key, [])
        form_str  = enrichment.get(f"{prefix}_last_5")  # may still be None if no stats
        if recent:
            matches = _parse_recent_matches(recent, team_id, n=5, form_str=form_str)
            if matches is not None:
                enrichment[f"{prefix}_recent_matches"] = json.dumps(matches)
            # else: leave as None — alignment failed, frontend falls back to "W · Seier"

    # ── Phase 12 — Fixture statistics aggregation ───────────────────────────────
    # Aggregate possession, shots, corners, fouls, cards, pass accuracy, and xG
    # from /fixtures/statistics across recent completed matches (same league+season).
    # Reuses recent_cache fixture lists populated above for Phase 11.
    # fix_stats_cache is keyed by af_fixture_id — one call returns both teams' stats.
    for team_id, prefix in [(af_home_id, "home"), (af_away_id, "away")]:
        cache_key = (team_id, af_league_id, af_season)
        recent = recent_cache.get(cache_key, [])
        if recent:
            agg = _aggregate_fixture_stats(recent, team_id, fix_stats_cache)
            if agg:
                enrichment[f"{prefix}_recent_fixture_stats"] = json.dumps(agg)

    # ── AF Predictions (optional reference data only) ─────────────────────────
    # Stored as reference data. Do NOT use for H/U/B probabilities or picks.
    if fetch_predictions:
        try:
            pred = get_predictions(af_fixture_id)
            if pred:
                pcts   = pred.get("predictions", {}).get("percent", {})
                advice = pred.get("predictions", {}).get("advice")
                enrichment["api_prediction_home"]   = _parse_pct(pcts.get("home"))
                enrichment["api_prediction_draw"]   = _parse_pct(pcts.get("draw"))
                enrichment["api_prediction_away"]   = _parse_pct(pcts.get("away"))
                enrichment["api_prediction_advice"] = advice

                # Phase 10 — comparison ratings
                comp = pred.get("comparison", {})
                enrichment["api_comparison_att_home"]   = _parse_pct(comp.get("att",   {}).get("home"))
                enrichment["api_comparison_att_away"]   = _parse_pct(comp.get("att",   {}).get("away"))
                enrichment["api_comparison_def_home"]   = _parse_pct(comp.get("def",   {}).get("home"))
                enrichment["api_comparison_def_away"]   = _parse_pct(comp.get("def",   {}).get("away"))
                enrichment["api_comparison_form_home"]  = _parse_pct(comp.get("form",  {}).get("home"))
                enrichment["api_comparison_form_away"]  = _parse_pct(comp.get("form",  {}).get("away"))
                enrichment["api_comparison_total_home"] = _parse_pct(comp.get("total", {}).get("home"))
                enrichment["api_comparison_total_away"] = _parse_pct(comp.get("total", {}).get("away"))
        except Exception:
            pass

    return enrichment


def _date_range(kick_date: str) -> tuple[str, str]:
    """
    Return (from_date, to_date) covering the match date ± timezone slippage.
    NT times are in CEST (UTC+2), so a midnight-local match sits on the
    previous UTC day. Fetching from kick_date-1 to kick_date handles this.
    """
    try:
        d = date.fromisoformat(kick_date)
        return (d - timedelta(days=1)).isoformat(), kick_date
    except (ValueError, TypeError):
        return kick_date, kick_date


def enrich_active_fixtures(
    week: int,
    year: int,
    verbose: bool = True,
    fetch_predictions: bool = False,
    skip_already_enriched: bool = False,
) -> dict:
    """
    Match all active NT fixtures for the given week to API-Football,
    fetch statistical enrichment (standings, form, goals), and persist to the DB.

    AF predictions are skipped by default. Pass fetch_predictions=True only when
    you want to store them as optional reference data.

    skip_already_enriched=True skips fixtures that already have both an AF link
    and has_api_football_data=1 — useful in daily mode to avoid redundant calls.

    Returns a summary dict with counts and average match confidence.
    """
    from config import API_FOOTBALL_KEY
    if not API_FOOTBALL_KEY:
        raise EnvironmentError("API_FOOTBALL_KEY not set — cannot enrich fixtures.")

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Collect already-enriched fixture IDs when skipping is requested
    already_enriched: set[str] = set()
    if skip_already_enriched:
        from db.connection import get_conn
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT lnk.fixture_id
                   FROM api_football_fixture_links lnk
                   JOIN fixture_stat_enrichment e ON e.fixture_id = lnk.fixture_id
                   WHERE e.has_api_football_data = 1"""
            ).fetchall()
            already_enriched = {r[0] for r in rows}

    # Collect all NT fixtures with competition mapping
    all_nt: list[dict] = []
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            fid = m["fixture_id"]
            if fid in already_enriched:
                continue
            ko  = m.get("kickoff_utc", "")
            arr = m.get("arrangement_name") or m.get("competition_id") or ""
            lid, season, status = map_nt_competition(arr)
            all_nt.append({
                "fixture_id":   fid,
                "arrangement":  arr,
                "home_name":    m["home_name"],
                "away_name":    m["away_name"],
                "kick_date":    ko[:10],
                "af_league_id": lid,
                "af_season":    season,
                "af_status":    status,
            })

    # Session-level caches to batch API calls
    af_fix_cache:    dict[tuple, list[dict]] = {}
    standings_cache: dict[tuple, list[dict]] = {}
    stats_cache:     dict[tuple, dict | None] = {}
    recent_cache:    dict[tuple, list[dict]] = {}    # (team_id, league_id, season) → last 5 fixtures
    fix_stats_cache: dict[int, list[dict]] = {}      # af_fixture_id → /fixtures/statistics response

    n_total      = len(all_nt)
    n_skipped    = 0
    n_matched    = 0
    n_stored     = 0
    n_failed     = 0
    total_conf   = 0.0

    for f in all_nt:
        lid    = f["af_league_id"]
        season = f["af_season"]
        status = f["af_status"]

        if status == "not_covered":
            n_skipped += 1
            continue

        # If competition is unknown or has no mapped league, skip to date-based fallback below
        if lid is None:
            matched_af = None
            confidence = 0.0
        else:
            from_d, to_d = _date_range(f["kick_date"])
            cache_key = (lid, season, from_d, to_d)

            if cache_key not in af_fix_cache:
                try:
                    af_fix_cache[cache_key] = get_fixtures(
                        league_id=lid, season=season, from_date=from_d, to_date=to_d
                    )
                except Exception as exc:
                    if verbose:
                        print(f"  [WARN] AF fixtures fetch failed (league {lid}): {exc}")
                    af_fix_cache[cache_key] = []

            matched_af, confidence = _match_to_af(
                f["home_name"], f["away_name"], af_fix_cache[cache_key]
            )

        # When competition-map match fails, try date-based cross-league fallback
        if not matched_af and status in ("unknown", "probe"):
            fb_fix, fb_conf, fb_lid, fb_season, fb_league, fb_country = _search_af_fixture_fallback(
                f["home_name"], f["away_name"], f["kick_date"], verbose=verbose
            )
            if fb_fix:
                matched_af = fb_fix
                confidence = fb_conf
                # Carry fallback league data so the link below uses the right IDs
                lid    = fb_lid
                season = fb_season
                f["_fallback_league"]  = fb_league
                f["_fallback_country"] = fb_country
                f["_link_source"]      = "auto_link_fallback"
            else:
                n_failed += 1
                if verbose:
                    print(f"  [MISS] {f['home_name']:<22} vs {f['away_name']:<22}  (no competition map + fallback miss)")
                continue
        elif not matched_af:
            n_failed += 1
            if verbose:
                print(f"  [MISS] {f['home_name']:<22} vs {f['away_name']:<22}  (league {lid})")
            continue

        n_matched  += 1
        total_conf += confidence

        af_fix_id  = matched_af["fixture"]["id"]
        af_home_id = matched_af["teams"]["home"]["id"]
        af_away_id = matched_af["teams"]["away"]["id"]
        # Logos from the already-fetched fixture response (fallback; standings logo preferred)
        home_logo  = matched_af["teams"]["home"].get("logo")
        away_logo  = matched_af["teams"]["away"].get("logo")

        upsert_fixture_link(
            fixture_id      = f["fixture_id"],
            af_fixture_id   = af_fix_id,
            af_league_id    = lid,
            af_season       = season,
            af_home_team_id = af_home_id,
            af_away_team_id = af_away_id,
            match_confidence = confidence,
            link_source     = f.get("_link_source", "competition_map"),
            af_league_name  = f.get("_fallback_league"),
            af_country      = f.get("_fallback_country"),
        )

        try:
            enrichment = _fetch_enrichment(
                af_fix_id, lid, season, af_home_id, af_away_id,
                standings_cache, stats_cache, recent_cache, fix_stats_cache,
                home_logo_url=home_logo,
                away_logo_url=away_logo,
                fetch_predictions=fetch_predictions,
            )
            upsert_stat_enrichment(f["fixture_id"], **enrichment)
            n_stored += 1

            if verbose:
                pos_h  = enrichment.get("home_position") or "?"
                pos_a  = enrichment.get("away_position") or "?"
                form_h = enrichment.get("home_last_5") or "—"
                form_a = enrichment.get("away_last_5") or "—"
                print(
                    f"  [OK]  {f['home_name']:<22} vs {f['away_name']:<22}"
                    f"  pos={pos_h}/{pos_a}  form={form_h}/{form_a}"
                    f"  conf={confidence:.2f}"
                )
        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f"  [ERR] {f['home_name']} vs {f['away_name']}: {exc}")

    avg_conf = (total_conf / n_matched) if n_matched else 0.0
    n_attempted = n_total - n_skipped

    return {
        "n_total":       n_total,
        "n_skipped":     n_skipped,
        "n_attempted":   n_attempted,
        "n_matched":     n_matched,
        "n_stored":      n_stored,
        "n_failed":      n_failed,
        "avg_confidence": avg_conf,
    }


def _fetch_and_insert_wc_fixture(
    conn, nt_home: str, nt_away: str, nt_date: str, verbose: bool = False
) -> dict | None:
    """
    For an NT Oddsen fixture not yet in the DB, try to find it in the WC 2026
    via API-Football and insert it (fixture + AF link + bookmaker odds if available).
    Returns a dict with fixture info (matching model_map format) or None.
    """
    import uuid
    import time as _time
    from ingestion.api_football import get_fixtures as af_get_fixtures

    try:
        d0 = date.fromisoformat(nt_date)
    except (ValueError, TypeError):
        return None

    from_d = (d0 - timedelta(days=1)).isoformat()
    to_d   = (d0 + timedelta(days=1)).isoformat()

    try:
        af_fixtures = af_get_fixtures(league_id=1, season=2026, from_date=from_d, to_date=to_d)
    except Exception as exc:
        if verbose:
            print(f"    [ERR] WC AF fixtures fetch for {nt_date}: {exc}")
        return None

    if not af_fixtures:
        if verbose:
            print(f"    [MISS] No WC AF fixtures found for date {nt_date}")
        return None

    matched_af, confidence = _match_to_af(nt_home, nt_away, af_fixtures)
    if not matched_af:
        if verbose:
            print(f"    [MISS] No AF match for '{nt_home}' vs '{nt_away}' in WC fixtures")
        return None

    af_id     = matched_af["fixture"]["id"]
    kickoff   = matched_af["fixture"].get("date", "")
    home_name = matched_af["teams"]["home"]["name"]
    away_name = matched_af["teams"]["away"]["name"]
    af_home   = matched_af["teams"]["home"]["id"]
    af_away   = matched_af["teams"]["away"]["id"]

    if verbose:
        print(f"    [FOUND] {home_name} vs {away_name}  af_id={af_id}  conf={confidence:.2f}")

    # Insert fixture + AF link (idempotent via CONFLICT/IGNORE)
    fid = str(uuid.uuid4())
    conn.execute(
        """INSERT INTO fixtures
               (fixture_id, kickoff_utc, external_id, home_name, away_name, created_at)
           VALUES (?,?,?,?,?,datetime('now'))
           ON CONFLICT(external_id) DO UPDATE
               SET home_name=excluded.home_name, away_name=excluded.away_name""",
        (fid, kickoff, af_id, home_name, away_name),
    )
    existing = conn.execute(
        "SELECT fixture_id FROM fixtures WHERE external_id=?", (af_id,)
    ).fetchone()
    real_fid = existing[0] if existing else fid

    conn.execute(
        """INSERT OR IGNORE INTO api_football_fixture_links
               (fixture_id, api_football_fixture_id, api_football_league_id,
                api_football_season, api_football_home_team_id,
                api_football_away_team_id, match_confidence)
           VALUES (?,?,?,?,?,?,?)""",
        (real_fid, af_id, 1, 2026, af_home, af_away, confidence),
    )
    conn.commit()

    # Try to fetch and store bookmaker odds for this new fixture
    try:
        from ingestion.api_football_odds import fetch_af_all_markets, _store_market_odds
        _time.sleep(2.1)
        best = fetch_af_all_markets(af_id)
        if best:
            if "1X2" in best:
                bkm, rows = best["1X2"]
                sel_map = {r["selection"]: r["odds"] for r in rows}
                try:
                    h_o = sel_map["HOME"]
                    u_o = sel_map["DRAW"]
                    b_o = sel_map["AWAY"]
                    conn.execute(
                        "INSERT OR IGNORE INTO odds (fixture_id, source, odds_h, odds_u, odds_b)"
                        " VALUES (?,?,?,?,?)",
                        (real_fid, f"api_football:{bkm}", h_o, u_o, b_o),
                    )
                    conn.commit()
                    if verbose:
                        print(f"    [ODDS]  1X2 {bkm}: H={h_o} U={u_o} B={b_o}")
                except KeyError:
                    pass
            _store_market_odds(conn, real_fid, af_id, best, verbose=False)
            conn.commit()
    except Exception as exc:
        if verbose:
            print(f"    [WARN]  Odds fetch failed for af_id={af_id}: {exc}")

    return {
        "fixture_id":                real_fid,
        "kickoff_utc":               kickoff,
        "home_name":                 home_name,
        "away_name":                 away_name,
        "api_football_fixture_id":   af_id,
        "api_football_league_id":    1,
        "api_football_season":       2026,
        "api_football_home_team_id": af_home,
        "api_football_away_team_id": af_away,
        "has_api_football_data":     0,
    }


def enrich_nt_oddsen_fixtures(
    verbose: bool = True,
    max_snapshot_age_hours: int = 12,
) -> dict:
    """
    Ensure every NT Oddsen fixture has a fixture_stat_enrichment row.
    Called before generate_global_bet_candidates() to maximise full_model coverage.

    1. Load NT fixture keys from nt_oddsen_odds_snapshot (recent snapshot only).
    2. For each key, find the matching internal fixture_id using normalized team
       names + date (±1 day tolerance).
    3. If no match: try to fetch the WC fixture from AF API and insert it.
    4. If match found but enrichment is missing: run _fetch_enrichment() and upsert.
    """
    from config import API_FOOTBALL_KEY
    if not API_FOOTBALL_KEY:
        return {"error": "API_FOOTBALL_KEY not set"}

    from db.connection import get_conn
    from db.enrichment import upsert_stat_enrichment
    from ingestion.nt_oddsen_playwright import normalize_team_name as nt_norm

    conn = get_conn()
    age_threshold = (
        datetime.now(timezone.utc) - timedelta(hours=max_snapshot_age_hours)
    ).isoformat()

    # 1. NT fixture keys from recent snapshot
    nt_rows = conn.execute(
        """SELECT DISTINCT fixture_key
           FROM nt_oddsen_odds_snapshot
           WHERE scraped_at >= ?""",
        (age_threshold,),
    ).fetchall()

    if not nt_rows:
        conn.close()
        return {
            "n_nt_keys": 0, "n_newly_enriched": 0,
            "message": f"No NT snapshot within last {max_snapshot_age_hours}h",
        }

    nt_keys = [r["fixture_key"] for r in nt_rows]
    n_nt_keys = len(nt_keys)

    # 2. Build model_map: normalized_key -> fixture row (with ±1 day date variants)
    existing = conn.execute(
        """SELECT f.fixture_id, f.kickoff_utc, f.home_name, f.away_name,
                  lnk.api_football_fixture_id,
                  lnk.api_football_league_id,
                  lnk.api_football_season,
                  lnk.api_football_home_team_id,
                  lnk.api_football_away_team_id,
                  e.has_api_football_data
           FROM fixtures f
           JOIN api_football_fixture_links lnk ON lnk.fixture_id = f.fixture_id
           LEFT JOIN fixture_stat_enrichment e ON e.fixture_id = f.fixture_id
           WHERE f.kickoff_utc > datetime('now', '-2 days')""",
    ).fetchall()

    model_map: dict[str, dict] = {}
    for row in existing:
        ko = (row["kickoff_utc"] or "")[:10]
        h  = nt_norm(row["home_name"])
        a  = nt_norm(row["away_name"])
        base = f"{h}|{a}|{ko}"
        model_map[base] = dict(row)
        try:
            d0 = date.fromisoformat(ko)
            for delta in (1, -1):
                alt = f"{h}|{a}|{(d0 + timedelta(days=delta)).isoformat()}"
                if alt not in model_map:
                    model_map[alt] = dict(row)
        except (ValueError, TypeError):
            pass

    # 3. Shared caches for this enrichment session
    standings_cache: dict = {}
    stats_cache: dict = {}
    recent_cache: dict = {}
    fix_stats_cache: dict = {}

    n_already_enriched = 0
    n_newly_enriched   = 0
    n_fetched_new      = 0
    n_no_af_link       = 0
    n_failed           = 0

    for nt_key in nt_keys:
        parts = nt_key.split("|")
        if len(parts) < 3:
            continue
        nt_h, nt_a, nt_date = parts[0], parts[1], parts[2]

        mf = model_map.get(nt_key)

        if mf is None:
            if verbose:
                print(f"  [MISS]  {nt_h} vs {nt_a} ({nt_date}) — not in DB, trying AF WC fetch...")
            mf = _fetch_and_insert_wc_fixture(conn, nt_h, nt_a, nt_date, verbose=verbose)
            if mf:
                n_fetched_new += 1
                ko = (mf["kickoff_utc"] or "")[:10]
                h_n = nt_norm(mf["home_name"])
                a_n = nt_norm(mf["away_name"])
                model_map[f"{h_n}|{a_n}|{ko}"] = mf
            else:
                n_no_af_link += 1
                continue

        # Skip if already has full enrichment data
        if mf.get("has_api_football_data") == 1:
            n_already_enriched += 1
            if verbose:
                print(f"  [SKIP]  {nt_h} vs {nt_a} — enrichment already present")
            continue

        af_fix_id = mf.get("api_football_fixture_id")
        af_lid    = mf.get("api_football_league_id")
        af_season = mf.get("api_football_season")
        af_home   = mf.get("api_football_home_team_id")
        af_away   = mf.get("api_football_away_team_id")

        if not all([af_fix_id, af_lid, af_season, af_home, af_away]):
            n_no_af_link += 1
            if verbose:
                print(f"  [SKIP]  {nt_h} vs {nt_a} — AF link incomplete")
            continue

        if verbose:
            print(f"  [ENRICH] {nt_h} vs {nt_a}  (af_fix={af_fix_id}, league={af_lid}/{af_season})")

        try:
            enrichment = _fetch_enrichment(
                af_fix_id, af_lid, af_season, af_home, af_away,
                standings_cache, stats_cache, recent_cache, fix_stats_cache,
                fetch_predictions=False,
            )
            upsert_stat_enrichment(mf["fixture_id"], **enrichment)
            n_newly_enriched += 1
            if verbose:
                pos_h  = enrichment.get("home_position") or "?"
                pos_a  = enrichment.get("away_position") or "?"
                form_h = enrichment.get("home_last_5") or "—"
                form_a = enrichment.get("away_last_5") or "—"
                print(f"    -> pos={pos_h}/{pos_a}  form={form_h}/{form_a}")
        except Exception as exc:
            n_failed += 1
            if verbose:
                print(f"  [ERR]   {nt_h} vs {nt_a}: {exc}")

    conn.close()

    return {
        "n_nt_keys":          n_nt_keys,
        "n_already_enriched": n_already_enriched,
        "n_newly_enriched":   n_newly_enriched,
        "n_fetched_new":      n_fetched_new,
        "n_no_af_link":       n_no_af_link,
        "n_failed":           n_failed,
    }


# ── Auto-link fallback: date-based cross-league fixture search ────────────────

def _score_match_fallback(home_en: str, away_en: str, af_home: str, af_away: str) -> float:
    """
    Score a team-name pair match 0.0–1.0.
    Combines exact, substring, and token-overlap checks.
    Used for the date-based fallback when the competition is not in _NT_COMPETITION_MAP.
    """
    def _sim(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if len(a) >= 4 and a in b:
            return 0.90
        if len(b) >= 4 and b in a:
            return 0.90
        # Token-set overlap
        ta = set(a.split())
        tb = set(b.split())
        if ta and tb:
            overlap = len(ta & tb) / max(len(ta), len(tb))
            if overlap >= 0.5:
                return 0.70
        # 4-char prefix
        if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4]:
            return 0.60
        return 0.0

    h = _sim(home_en, af_home)
    a = _sim(away_en, af_away)
    if h == 0.0 and a == 0.0:
        return 0.0
    return (h + a) / 2.0


def _search_af_fixture_fallback(
    nt_home:    str,
    nt_away:    str,
    kick_date:  str,         # YYYY-MM-DD local date
    verbose:    bool = False,
) -> tuple[dict | None, float, int | None, int | None, str | None, str | None]:
    """
    Search for an AF fixture by date across ALL leagues when no competition mapping exists.

    Calls GET /fixtures?date=YYYY-MM-DD (returns all fixtures on that date globally),
    then fuzzy-matches team names.

    Returns:
        (af_fixture, confidence, af_league_id, af_season, league_name, country)
        or (None, 0.0, None, None, None, None) if no match above threshold.
    """
    from ingestion.api_football import get_fixtures, translate_team_name

    home_en = translate_team_name(nt_home)
    away_en = translate_team_name(nt_away)

    # Try kick_date and the day before (CEST offset can push UTC date back)
    dates_to_try: list[str] = [kick_date]
    try:
        from datetime import date as _date, timedelta
        d = _date.fromisoformat(kick_date)
        dates_to_try = [(d - timedelta(days=1)).isoformat(), kick_date]
    except (ValueError, TypeError):
        pass

    best_fixture:     dict | None = None
    best_score:       float       = 0.0
    best_league_id:   int | None  = None
    best_season:      int | None  = None
    best_league_name: str | None  = None
    best_country:     str | None  = None
    seen: set[int] = set()

    for date_str in dates_to_try:
        try:
            fixtures = get_fixtures(date=date_str)
        except Exception as exc:
            if verbose:
                print(f"  [FALLBACK] date fetch failed ({date_str}): {exc}")
            continue

        for af in fixtures:
            af_id = af.get("fixture", {}).get("id")
            if af_id in seen:
                continue
            seen.add(af_id)

            af_home = translate_team_name(af.get("teams", {}).get("home", {}).get("name", ""))
            af_away = translate_team_name(af.get("teams", {}).get("away", {}).get("name", ""))

            score = _score_match_fallback(home_en, away_en, af_home, af_away)
            if score > best_score:
                best_score       = score
                best_fixture     = af
                best_league_id   = af.get("league", {}).get("id")
                best_season      = af.get("league", {}).get("season")
                best_league_name = af.get("league", {}).get("name")
                best_country     = af.get("league", {}).get("country")

    _FALLBACK_THRESHOLD = 0.80
    if best_score >= _FALLBACK_THRESHOLD:
        if verbose:
            home_n = best_fixture["teams"]["home"]["name"]
            away_n = best_fixture["teams"]["away"]["name"]
            print(
                f"  [FALLBACK OK]  '{nt_home}' vs '{nt_away}' -> "
                f"'{home_n}' vs '{away_n}'  "
                f"league={best_league_id} ({best_league_name}, {best_country})  "
                f"score={best_score:.2f}"
            )
        return best_fixture, best_score, best_league_id, best_season, best_league_name, best_country

    if verbose and best_score > 0:
        home_n = best_fixture["teams"]["home"]["name"] if best_fixture else "?"
        away_n = best_fixture["teams"]["away"]["name"] if best_fixture else "?"
        print(
            f"  [FALLBACK MISS]  '{nt_home}' vs '{nt_away}' "
            f"best={best_score:.2f} ('{home_n}' vs '{away_n}') — below threshold"
        )
    return None, 0.0, None, None, None, None


def auto_link_unresolved_coupon_fixtures(
    week:    int,
    year:    int,
    verbose: bool = True,
) -> dict:
    """
    For each NT coupon fixture that has no AF link and no valid competition mapping,
    attempt a date-based cross-league search on API-Football.

    On success:
    - Inserts api_football_fixture_links with link_source='auto_link_fallback'
    - Runs _fetch_enrichment() to populate fixture_stat_enrichment
    - Returns a summary dict

    Fixtures with unknown opponents (W80 pattern) are classified and skipped.
    """
    from config import API_FOOTBALL_KEY
    if not API_FOOTBALL_KEY:
        return {"error": "API_FOOTBALL_KEY not set"}

    from db.connection import get_conn
    from db.coupon import list_coupons, get_coupon_matches
    from db.enrichment import upsert_fixture_link, upsert_stat_enrichment
    from ingestion.api_football import map_nt_competition
    import re

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Build a set of fixture_ids that already have AF links
    with get_conn() as _c:
        linked_fids = {
            r[0] for r in _c.execute(
                "SELECT fixture_id FROM api_football_fixture_links"
            ).fetchall()
        }

    standings_cache:  dict = {}
    stats_cache:      dict = {}
    recent_cache:     dict = {}
    fix_stats_cache:  dict = {}

    n_total       = 0
    n_already     = 0
    n_skipped     = 0
    n_auto_linked = 0
    n_enriched    = 0
    n_failed      = 0
    unresolved:   list[str] = []

    for coupon in coupons:
        for m in get_coupon_matches(coupon["coupon_id"]):
            fid = m["fixture_id"]
            n_total += 1

            # Already linked — skip
            if fid in linked_fids:
                n_already += 1
                continue

            home = m.get("home_name", "") or ""
            away = m.get("away_name", "") or ""
            arr  = m.get("arrangement_name") or m.get("competition_id") or ""
            ko   = (m.get("kickoff_utc") or "")[:10]  # YYYY-MM-DD

            # Unknown opponent pattern (W80, W81, … = TBD WC/tournament bracket slot)
            away_id = m.get("away_team_id") or ""
            if re.match(r"^w\d+", away_id.lower()):
                n_skipped += 1
                if verbose:
                    print(f"  [SKIP]  {home} vs {away} — unknown opponent ({away_id})")
                continue

            # Check if competition is "not_covered" (known unmappable league)
            _, _, status = map_nt_competition(arr)
            if status == "not_covered":
                # Still try date fallback — "not_covered" means the competition map
                # has no entry but the fixture may exist in AF under a different league
                pass

            if verbose:
                print(f"  [TRY]  {home} vs {away}  ({arr}, {ko})")

            af_fix, conf, af_lid, af_season, league_name, country = _search_af_fixture_fallback(
                home, away, ko, verbose=verbose
            )

            if af_fix is None:
                n_failed += 1
                unresolved.append(f"{home} vs {away} ({arr})")
                if verbose:
                    print(f"  [UNRESOLVED]  {home} vs {away}")
                continue

            af_fix_id  = af_fix["fixture"]["id"]
            af_home_id = af_fix["teams"]["home"]["id"]
            af_away_id = af_fix["teams"]["away"]["id"]

            upsert_fixture_link(
                fixture_id      = fid,
                af_fixture_id   = af_fix_id,
                af_league_id    = af_lid,
                af_season       = af_season,
                af_home_team_id = af_home_id,
                af_away_team_id = af_away_id,
                match_confidence = conf,
                link_source     = "auto_link_fallback",
                af_league_name  = league_name,
                af_country      = country,
            )
            linked_fids.add(fid)
            n_auto_linked += 1

            try:
                enrichment = _fetch_enrichment(
                    af_fix_id, af_lid, af_season, af_home_id, af_away_id,
                    standings_cache, stats_cache, recent_cache, fix_stats_cache,
                )
                upsert_stat_enrichment(fid, **enrichment)
                n_enriched += 1
            except Exception as exc:
                n_failed += 1
                if verbose:
                    print(f"  [ERR]  enrichment for {home} vs {away}: {exc}")

    return {
        "n_total":       n_total,
        "n_already":     n_already,
        "n_skipped":     n_skipped,
        "n_auto_linked": n_auto_linked,
        "n_enriched":    n_enriched,
        "n_failed":      n_failed,
        "unresolved":    unresolved,
    }
