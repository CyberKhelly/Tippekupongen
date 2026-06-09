import json
import uuid
from db.connection import get_conn


# ── Fixtures ────────────────────────────────────────────────────────────────────

def upsert_fixture(
    home_team_id: str,
    away_team_id: str,
    competition_id: str,
    kickoff_utc: str,
    matchday: int | None = None,
    venue: str | None = None,
    external_id: int | None = None,
    nt_match_id: str | None = None,
    betradar_match_id: int | None = None,
    arrangement_name: str | None = None,
    source: str | None = None,
) -> str:
    """Insert or update a fixture. Returns the fixture_id."""
    with get_conn() as conn:
        # Prefer NT match ID as the stable upsert key
        if nt_match_id is not None:
            row = conn.execute(
                "SELECT fixture_id FROM fixtures WHERE nt_match_id = ?",
                (nt_match_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE fixtures
                       SET home_team_id=?, away_team_id=?, competition_id=?,
                           kickoff_utc=?, matchday=?, venue=?,
                           betradar_match_id=COALESCE(?, betradar_match_id),
                           arrangement_name=COALESCE(?, arrangement_name),
                           source=COALESCE(?, source)
                       WHERE nt_match_id=?""",
                    (home_team_id, away_team_id, competition_id,
                     kickoff_utc, matchday, venue,
                     betradar_match_id, arrangement_name, source,
                     nt_match_id),
                )
                return row["fixture_id"]

        # Fall back to legacy external_id key
        if external_id is not None:
            row = conn.execute(
                "SELECT fixture_id FROM fixtures WHERE external_id = ?",
                (external_id,),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE fixtures
                       SET home_team_id=?, away_team_id=?, competition_id=?,
                           kickoff_utc=?, matchday=?, venue=?
                       WHERE external_id=?""",
                    (home_team_id, away_team_id, competition_id,
                     kickoff_utc, matchday, venue, external_id),
                )
                return row["fixture_id"]

        fixture_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO fixtures
               (fixture_id, home_team_id, away_team_id, competition_id,
                kickoff_utc, matchday, venue, external_id,
                nt_match_id, betradar_match_id, arrangement_name, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (fixture_id, home_team_id, away_team_id, competition_id,
             kickoff_utc, matchday, venue, external_id,
             nt_match_id, betradar_match_id, arrangement_name, source),
        )
    return fixture_id


# ── Odds ────────────────────────────────────────────────────────────────────────

def upsert_odds(
    fixture_id: str,
    source: str,
    odds_h: float,
    odds_u: float,
    odds_b: float,
) -> None:
    """Append a new odds row (keeps history; latest row wins in queries)."""
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO odds (fixture_id, source, odds_h, odds_u, odds_b)
               VALUES (?, ?, ?, ?, ?)""",
            (fixture_id, source, odds_h, odds_u, odds_b),
        )


def get_best_odds(fixture_id: str) -> dict | None:
    """
    Return the most authoritative odds row for a fixture.
    Priority: pinnacle > norsk_tipping > manual > any.
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT odds_h, odds_u, odds_b, source
               FROM odds
               WHERE fixture_id = ?
               ORDER BY
                   CASE source
                       WHEN 'pinnacle'      THEN 1
                       WHEN 'norsk_tipping' THEN 2
                       WHEN 'manual'        THEN 3
                       ELSE 4
                   END,
                   fetched_at DESC
               LIMIT 1""",
            (fixture_id,),
        ).fetchone()
    return dict(row) if row else None


# ── Tips percentages ─────────────────────────────────────────────────────────────
# Expert tips and public/people tips are stored separately from odds.
# They are crowd/sentiment signals, NOT bookmaker probability estimates.
# Do not use them as the probability baseline.

def upsert_tips(
    coupon_id: str,
    fixture_id: str,
    expert_h: float | None,
    expert_u: float | None,
    expert_b: float | None,
    public_h: float | None,
    public_u: float | None,
    public_b: float | None,
) -> None:
    """Store expert and public tip percentages on the coupon_fixtures junction row."""
    with get_conn() as conn:
        conn.execute(
            """UPDATE coupon_fixtures
               SET expert_h=?, expert_u=?, expert_b=?,
                   public_h=?, public_u=?, public_b=?
               WHERE coupon_id=? AND fixture_id=?""",
            (expert_h, expert_u, expert_b,
             public_h, public_u, public_b,
             coupon_id, fixture_id),
        )


# ── Coupons ─────────────────────────────────────────────────────────────────────

def upsert_coupon(
    coupon_id: str,
    label: str,
    deadline_utc: str,
    week: int,
    year: int,
    nt_game_day_id: str | None = None,
    day_type: str | None = None,
    source: str | None = None,
    confidence: str | None = None,
    content_hash: str | None = None,
    last_synced_at: str | None = None,
) -> None:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO coupons
               (coupon_id, label, deadline_utc, week, year,
                nt_game_day_id, day_type, source, confidence,
                content_hash, last_synced_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(coupon_id) DO UPDATE SET
                   label          = excluded.label,
                   deadline_utc   = excluded.deadline_utc,
                   nt_game_day_id = COALESCE(excluded.nt_game_day_id, nt_game_day_id),
                   day_type       = COALESCE(excluded.day_type,       day_type),
                   source         = COALESCE(excluded.source,         source),
                   confidence     = COALESCE(excluded.confidence,     confidence),
                   content_hash   = COALESCE(excluded.content_hash,   content_hash),
                   last_synced_at = COALESCE(excluded.last_synced_at, last_synced_at),
                   updated_at     = excluded.updated_at""",
            (coupon_id, label, deadline_utc, week, year,
             nt_game_day_id, day_type, source, confidence,
             content_hash, last_synced_at, now),
        )


def add_coupon_fixture(
    coupon_id: str,
    fixture_id: str,
    match_number: int,
    arrangement_name: str | None = None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO coupon_fixtures
               (coupon_id, fixture_id, match_number, arrangement_name)
               VALUES (?, ?, ?, ?)""",
            (coupon_id, fixture_id, match_number, arrangement_name),
        )


def list_coupons(week: int | None = None, year: int | None = None) -> list[dict]:
    with get_conn() as conn:
        if week is not None and year is not None:
            rows = conn.execute(
                "SELECT * FROM coupons WHERE week=? AND year=? ORDER BY deadline_utc",
                (week, year),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM coupons ORDER BY deadline_utc DESC LIMIT 20"
            ).fetchall()
    return [dict(r) for r in rows]


def get_coupon_matches(coupon_id: str) -> list[dict]:
    """
    Return enriched match rows for a coupon ordered by match_number.
    Includes home/away display names, best available odds, and tips percentages.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT cf.match_number,
                      cf.arrangement_name,
                      cf.expert_h, cf.expert_u, cf.expert_b,
                      cf.public_h, cf.public_u, cf.public_b,
                      f.fixture_id, f.kickoff_utc, f.competition_id,
                      f.home_team_id, f.away_team_id,
                      f.nt_match_id, f.betradar_match_id,
                      f.source      AS fixture_source,
                      COALESCE(th.name_local, th.name_canonical) AS home_name,
                      COALESCE(ta.name_local, ta.name_canonical) AS away_name,
                      th.name_canonical AS home_name_en,
                      ta.name_canonical AS away_name_en,
                      th.nt_team_id    AS home_nt_team_id,
                      ta.nt_team_id    AS away_nt_team_id
               FROM coupon_fixtures cf
               JOIN fixtures f ON f.fixture_id = cf.fixture_id
               JOIN teams th   ON th.team_id   = f.home_team_id
               JOIN teams ta   ON ta.team_id   = f.away_team_id
               WHERE cf.coupon_id = ?
               ORDER BY cf.match_number""",
            (coupon_id,),
        ).fetchall()

        result = []
        for row in rows:
            rd = dict(row)
            odds = conn.execute(
                """SELECT odds_h, odds_u, odds_b, source
                   FROM odds WHERE fixture_id = ?
                   ORDER BY
                       CASE source
                           WHEN 'pinnacle'      THEN 1
                           WHEN 'norsk_tipping' THEN 2
                           WHEN 'manual'        THEN 3
                           ELSE 4
                       END,
                       fetched_at DESC
                   LIMIT 1""",
                (rd["fixture_id"],),
            ).fetchone()
            if odds:
                rd.update(dict(odds))
            else:
                rd["odds_h"] = rd["odds_u"] = rd["odds_b"] = None
                rd["source"] = None
            result.append(rd)

    return result


# ── Coupon log ──────────────────────────────────────────────────────────────────

def log_coupon_event(coupon_id: str, event: str, detail: dict | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO coupon_log (coupon_id, event, detail) VALUES (?, ?, ?)",
            (coupon_id, event, json.dumps(detail) if detail else None),
        )
