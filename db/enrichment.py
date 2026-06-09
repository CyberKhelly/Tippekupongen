"""
CRUD for Phase 4B statistical enrichment tables.

api_football_fixture_links  — maps NT fixture_id to AF fixture ID + team IDs
fixture_stat_enrichment     — standings, form, goals, predictions per fixture
"""
from __future__ import annotations
from datetime import datetime, timezone

from db.connection import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Fixture links ─────────────────────────────────────────────────────────────

def upsert_fixture_link(
    fixture_id:         str,
    af_fixture_id:      int,
    af_league_id:       int,
    af_season:          int,
    af_home_team_id:    int | None,
    af_away_team_id:    int | None,
    match_confidence:   float,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO api_football_fixture_links
               (fixture_id, api_football_fixture_id, api_football_league_id,
                api_football_season, api_football_home_team_id,
                api_football_away_team_id, match_confidence, matched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(fixture_id) DO UPDATE SET
                   api_football_fixture_id   = excluded.api_football_fixture_id,
                   api_football_league_id    = excluded.api_football_league_id,
                   api_football_season       = excluded.api_football_season,
                   api_football_home_team_id = excluded.api_football_home_team_id,
                   api_football_away_team_id = excluded.api_football_away_team_id,
                   match_confidence          = excluded.match_confidence,
                   matched_at                = excluded.matched_at""",
            (fixture_id, af_fixture_id, af_league_id, af_season,
             af_home_team_id, af_away_team_id, match_confidence, _now()),
        )


def get_fixture_link(fixture_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM api_football_fixture_links WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    return dict(row) if row else None


def list_fixture_links(fixture_ids: list[str]) -> dict[str, dict]:
    if not fixture_ids:
        return {}
    placeholders = ",".join("?" for _ in fixture_ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM api_football_fixture_links WHERE fixture_id IN ({placeholders})",
            fixture_ids,
        ).fetchall()
    return {r["fixture_id"]: dict(r) for r in rows}


# ── Stat enrichment ───────────────────────────────────────────────────────────

def upsert_stat_enrichment(fixture_id: str, **data) -> None:
    if not data:
        return
    fields = list(data.keys()) + ["updated_at"]
    values = list(data.values()) + [_now()]
    cols         = ", ".join(fields)
    placeholders = ", ".join("?" for _ in fields)
    updates      = ", ".join(f"{f} = excluded.{f}" for f in fields)
    with get_conn() as conn:
        conn.execute(
            f"""INSERT INTO fixture_stat_enrichment (fixture_id, {cols})
               VALUES (?, {placeholders})
               ON CONFLICT(fixture_id) DO UPDATE SET {updates}""",
            [fixture_id] + values,
        )


def get_stat_enrichment(fixture_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM fixture_stat_enrichment WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    return dict(row) if row else None


# ── Estimated priors (no-odds fallback) ──────────────────────────────────────

def upsert_estimated_prior(
    fixture_id:   str,
    estimated_h:  float,
    estimated_u:  float,
    estimated_b:  float,
    signals_used: list[str],
    confidence:   float,
) -> None:
    import json
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO fixture_estimated_prior
               (fixture_id, estimated_h, estimated_u, estimated_b,
                signals_used, confidence, source, computed_at)
               VALUES (?, ?, ?, ?, ?, ?, 'model_estimated', ?)
               ON CONFLICT(fixture_id) DO UPDATE SET
                   estimated_h  = excluded.estimated_h,
                   estimated_u  = excluded.estimated_u,
                   estimated_b  = excluded.estimated_b,
                   signals_used = excluded.signals_used,
                   confidence   = excluded.confidence,
                   computed_at  = excluded.computed_at""",
            (fixture_id, estimated_h, estimated_u, estimated_b,
             json.dumps(signals_used), confidence, _now()),
        )


def get_estimated_prior(fixture_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM fixture_estimated_prior WHERE fixture_id = ?",
            (fixture_id,),
        ).fetchone()
    return dict(row) if row else None


def get_coupon_enrichment(coupon_id: str) -> list[dict]:
    """
    Return all fixtures for a coupon joined with enrichment data and best odds.
    Columns include NT fixture info, odds source, and all fixture_stat_enrichment fields.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   cf.match_number,
                   cf.arrangement_name,
                   f.fixture_id,
                   f.kickoff_utc,
                   f.competition_id,
                   COALESCE(th.name_local, th.name_canonical) AS home_name,
                   COALESCE(ta.name_local, ta.name_canonical) AS away_name,
                   -- NT tip percentages (reference data, not used for recommendations)
                   cf.expert_h, cf.expert_u, cf.expert_b,
                   cf.public_h, cf.public_u, cf.public_b,
                   -- Best available odds (priority: pinnacle > nt > manual)
                   o.odds_h, o.odds_u, o.odds_b, o.source AS odds_source,
                   -- Enrichment
                   e.has_api_football_data,
                   e.league_name,
                   e.home_position,    e.away_position,
                   e.home_form,        e.away_form,
                   e.home_last_5,      e.away_last_5,
                   e.home_last_10,     e.away_last_10,
                   e.home_home_record, e.away_away_record,
                   e.home_goals_for,   e.home_goals_against,
                   e.away_goals_for,   e.away_goals_against,
                   e.api_prediction_home, e.api_prediction_draw,
                   e.api_prediction_away, e.api_prediction_advice,
                   e.updated_at        AS enrichment_updated_at,
                   -- Link metadata
                   lnk.match_confidence,
                   lnk.api_football_fixture_id,
                   lnk.api_football_league_id,
                   lnk.api_football_season,
                   -- Model-estimated prior (no bookmaker odds)
                   ep.estimated_h,
                   ep.estimated_u,
                   ep.estimated_b,
                   ep.signals_used AS estimated_signals,
                   ep.confidence   AS estimated_confidence
               FROM coupon_fixtures cf
               JOIN fixtures f      ON f.fixture_id = cf.fixture_id
               JOIN teams th        ON th.team_id   = f.home_team_id
               JOIN teams ta        ON ta.team_id   = f.away_team_id
               LEFT JOIN odds o ON o.id = (
                   SELECT id FROM odds oi
                   WHERE oi.fixture_id = f.fixture_id
                   ORDER BY CASE oi.source
                       WHEN 'pinnacle'      THEN 1
                       WHEN 'norsk_tipping' THEN 2
                       WHEN 'manual'        THEN 3
                       ELSE 4 END,
                       oi.fetched_at DESC
                   LIMIT 1
               )
               LEFT JOIN fixture_stat_enrichment e
                   ON e.fixture_id = f.fixture_id
               LEFT JOIN api_football_fixture_links lnk
                   ON lnk.fixture_id = f.fixture_id
               LEFT JOIN fixture_estimated_prior ep
                   ON ep.fixture_id = f.fixture_id
               WHERE cf.coupon_id = ?
               ORDER BY cf.match_number""",
            (coupon_id,),
        ).fetchall()
    return [dict(r) for r in rows]
