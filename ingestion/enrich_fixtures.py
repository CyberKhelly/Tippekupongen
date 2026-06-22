"""
Phase 4B: Statistical Enrichment Layer.

Fetches and stores API-Football context for active NT fixtures.
NT remains source of truth — API-Football only enriches existing fixtures.

Usage:
    from ingestion.enrich_fixtures import enrich_active_fixtures
    summary = enrich_active_fixtures(week=24, year=2026)
"""
from __future__ import annotations
from datetime import date, timedelta

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

        if status == "not_covered" or lid is None:
            n_skipped += 1
            continue

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

        if not matched_af:
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
            fixture_id=f["fixture_id"],
            af_fixture_id=af_fix_id,
            af_league_id=lid,
            af_season=season,
            af_home_team_id=af_home_id,
            af_away_team_id=af_away_id,
            match_confidence=confidence,
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
