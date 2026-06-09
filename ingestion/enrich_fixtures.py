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

from ingestion.api_football import (
    map_nt_competition, translate_team_name,
    get_fixtures, get_standings, get_team_statistics, get_predictions,
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


def _fetch_enrichment(
    af_fixture_id:   int,
    af_league_id:    int,
    af_season:       int,
    af_home_id:      int,
    af_away_id:      int,
    standings_cache: dict,
    stats_cache:     dict,
    fetch_predictions: bool = False,
) -> dict:
    """
    Fetch standings and team statistics for one matched AF fixture.
    Uses shared caches to avoid redundant API calls across fixtures.

    AF predictions are fetched only when fetch_predictions=True and stored as
    reference data. They do NOT influence any recommendations.
    """
    enrichment: dict = {
        "has_api_football_data":   1,
        "api_football_fixture_id": af_fixture_id,
        "api_football_league_id":  af_league_id,
        "api_football_season":     af_season,
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
        team_rank: dict[int, int] = {}
        for group in groups:
            for row in group:
                team_rank[row["team"]["id"]] = row["rank"]
        enrichment["home_position"] = team_rank.get(af_home_id)
        enrichment["away_position"] = team_rank.get(af_away_id)

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

        form = stats.get("form") or ""
        if form:
            enrichment[f"{prefix}_form"]    = form
            enrichment[f"{prefix}_last_5"]  = form[-5:]  if len(form) >= 5  else form
            enrichment[f"{prefix}_last_10"] = form[-10:] if len(form) >= 10 else form

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

        goals = stats.get("goals", {})
        gf = goals.get("for",     {}).get("total", {}).get("total") or 0
        ga = goals.get("against", {}).get("total", {}).get("total") or 0
        enrichment[f"{prefix}_goals_for"]     = gf
        enrichment[f"{prefix}_goals_against"] = ga

    # ── AF Predictions (optional reference data only) ─────────────────────────
    # These values are stored but never used for H/U/B probabilities or picks.
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
) -> dict:
    """
    Match all active NT fixtures for the given week to API-Football,
    fetch statistical enrichment (standings, form, goals), and persist to the DB.

    AF predictions are skipped by default. Pass fetch_predictions=True only when
    you want to store them as optional reference data.

    Returns a summary dict with counts and average match confidence.
    """
    from config import API_FOOTBALL_KEY
    if not API_FOOTBALL_KEY:
        raise EnvironmentError("API_FOOTBALL_KEY not set — cannot enrich fixtures.")

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        return {"error": f"No coupons for week {week}/{year}"}

    # Collect all NT fixtures with competition mapping
    all_nt: list[dict] = []
    for c in coupons:
        for m in get_coupon_matches(c["coupon_id"]):
            ko  = m.get("kickoff_utc", "")
            arr = m.get("arrangement_name") or m.get("competition_id") or ""
            lid, season, status = map_nt_competition(arr)
            all_nt.append({
                "fixture_id":   m["fixture_id"],
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
                standings_cache, stats_cache,
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
