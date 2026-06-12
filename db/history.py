"""
History CRUD — coupon_predictions, match_results, coupon_evaluations.

Predictions are immutable snapshots of what the app recommended at save time.
Results are entered manually after matches are played.
Evaluations are computed from predictions + results.
"""
import json
import uuid
from db.connection import get_conn


# ── Coverage type helpers ────────────────────────────────────────────────────────

def _coverage_type(picks: list[str]) -> str:
    n = len(picks)
    if n == 1:
        return "single"
    if n == 2:
        return "half_cover"
    return "full_cover"


def _result_1x2(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "H"
    if home_score < away_score:
        return "B"
    return "U"


# ── Predictions ─────────────────────────────────────────────────────────────────

def save_prediction(
    coupon_id: str,
    fixture_id: str,
    match_number: int,
    recommended_pick: str,
    picks: list[str],
    confidence: float,
    implied_prob_h: float,
    implied_prob_u: float,
    implied_prob_b: float,
    odds_h: float | None = None,
    odds_u: float | None = None,
    odds_b: float | None = None,
    odds_source: str | None = None,
    model_version: str = "v1",
    pub_prob_h: float | None = None,
    pub_prob_u: float | None = None,
    pub_prob_b: float | None = None,
    value_h: float | None = None,
    value_u: float | None = None,
    value_b: float | None = None,
    crowd_disagreement_score: float | None = None,
) -> str:
    """Insert or replace a prediction snapshot. Returns prediction_id."""
    pred_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO coupon_predictions
               (prediction_id, coupon_id, fixture_id, match_number,
                recommended_pick, coverage_type, selected_outcomes,
                confidence, implied_prob_h, implied_prob_u, implied_prob_b,
                odds_h, odds_u, odds_b, odds_source, model_version,
                pub_prob_h, pub_prob_u, pub_prob_b,
                value_h, value_u, value_b,
                crowd_disagreement_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(coupon_id, fixture_id) DO UPDATE SET
                   match_number             = excluded.match_number,
                   recommended_pick         = excluded.recommended_pick,
                   coverage_type            = excluded.coverage_type,
                   selected_outcomes        = excluded.selected_outcomes,
                   confidence               = excluded.confidence,
                   implied_prob_h           = excluded.implied_prob_h,
                   implied_prob_u           = excluded.implied_prob_u,
                   implied_prob_b           = excluded.implied_prob_b,
                   odds_h                   = excluded.odds_h,
                   odds_u                   = excluded.odds_u,
                   odds_b                   = excluded.odds_b,
                   odds_source              = excluded.odds_source,
                   model_version            = excluded.model_version,
                   pub_prob_h               = excluded.pub_prob_h,
                   pub_prob_u               = excluded.pub_prob_u,
                   pub_prob_b               = excluded.pub_prob_b,
                   value_h                  = excluded.value_h,
                   value_u                  = excluded.value_u,
                   value_b                  = excluded.value_b,
                   crowd_disagreement_score = excluded.crowd_disagreement_score,
                   created_at               = datetime('now')""",
            (pred_id, coupon_id, fixture_id, match_number,
             recommended_pick, _coverage_type(picks), json.dumps(sorted(picks)),
             confidence, implied_prob_h, implied_prob_u, implied_prob_b,
             odds_h, odds_u, odds_b, odds_source, model_version,
             pub_prob_h, pub_prob_u, pub_prob_b,
             value_h, value_u, value_b,
             crowd_disagreement_score),
        )
    return pred_id


def get_predictions(coupon_id: str) -> list[dict]:
    """Return all predictions for a coupon ordered by match_number."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT p.*, t_home.name_local AS home_name, t_away.name_local AS away_name,
                      COALESCE(t_home.name_local, t_home.name_canonical) AS home_display,
                      COALESCE(t_away.name_local, t_away.name_canonical) AS away_display
               FROM coupon_predictions p
               JOIN fixtures f      ON f.fixture_id  = p.fixture_id
               JOIN teams t_home    ON t_home.team_id = f.home_team_id
               JOIN teams t_away    ON t_away.team_id = f.away_team_id
               WHERE p.coupon_id = ?
               ORDER BY p.match_number""",
            (coupon_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["selected_outcomes"] = json.loads(d["selected_outcomes"])
        except Exception:
            d["selected_outcomes"] = []
        result.append(d)
    return result


def has_predictions(coupon_id: str) -> bool:
    with get_conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM coupon_predictions WHERE coupon_id=?",
            (coupon_id,),
        ).fetchone()[0]
    return n > 0


# ── Results ─────────────────────────────────────────────────────────────────────

def save_result(
    fixture_id: str,
    home_score: int,
    away_score: int,
    source: str = "manual",
) -> str:
    """Insert or replace a match result. Returns result_id."""
    result_id = str(uuid.uuid4())
    r1x2 = _result_1x2(home_score, away_score)
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO match_results
               (result_id, fixture_id, home_score, away_score,
                result_1x2, result_source, final_status)
               VALUES (?, ?, ?, ?, ?, ?, 'confirmed')
               ON CONFLICT(fixture_id) DO UPDATE SET
                   home_score    = excluded.home_score,
                   away_score    = excluded.away_score,
                   result_1x2    = excluded.result_1x2,
                   result_source = excluded.result_source,
                   final_status  = 'confirmed',
                   updated_at    = datetime('now')""",
            (result_id, fixture_id, home_score, away_score, r1x2, source),
        )
    return result_id


def get_result(fixture_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM match_results WHERE fixture_id=?", (fixture_id,)
        ).fetchone()
    return dict(row) if row else None


def get_results_for_coupon(coupon_id: str) -> list[dict]:
    """
    Join predictions + results for a coupon.
    Each row has prediction fields + result fields (result_1x2 may be None).
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   p.match_number,
                   p.fixture_id,
                   COALESCE(th.name_local, th.name_canonical) AS home_name,
                   COALESCE(ta.name_local, ta.name_canonical) AS away_name,
                   p.recommended_pick,
                   p.coverage_type,
                   p.selected_outcomes,
                   p.confidence,
                   p.implied_prob_h, p.implied_prob_u, p.implied_prob_b,
                   p.odds_h, p.odds_u, p.odds_b, p.odds_source,
                   r.home_score, r.away_score, r.result_1x2, r.final_status
               FROM coupon_predictions p
               JOIN fixtures f ON f.fixture_id = p.fixture_id
               JOIN teams th   ON th.team_id   = f.home_team_id
               JOIN teams ta   ON ta.team_id   = f.away_team_id
               LEFT JOIN match_results r ON r.fixture_id = p.fixture_id
               WHERE p.coupon_id = ?
               ORDER BY p.match_number""",
            (coupon_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["selected_outcomes"] = json.loads(d["selected_outcomes"])
        except Exception:
            d["selected_outcomes"] = []
        result.append(d)
    return result


# ── Evaluations ──────────────────────────────────────────────────────────────────

def compute_evaluation(coupon_id: str, total_rows: int, stake_nok: float) -> dict:
    """
    Compute evaluation metrics from existing predictions + results.
    Does NOT save — call save_evaluation() to persist.
    """
    rows = get_results_for_coupon(coupon_id)
    if not rows:
        return {"evaluation_status": "pending", "coupon_id": coupon_id}

    n_results = sum(1 for r in rows if r.get("result_1x2"))
    n_total = len(rows)

    correct_picks = sum(
        1 for r in rows
        if r.get("result_1x2") and r["recommended_pick"] == r["result_1x2"]
    )
    system_covered = sum(
        1 for r in rows
        if r.get("result_1x2") and r["result_1x2"] in r["selected_outcomes"]
    )

    if n_results == 0:
        status = "pending"
    elif n_results < n_total:
        status = "partial"
    else:
        status = "complete"

    return {
        "coupon_id":      coupon_id,
        "total_rows":     total_rows,
        "stake_nok":      stake_nok,
        "total_fixtures": n_total,
        "correct_picks":  correct_picks   if n_results > 0 else None,
        "system_covered": system_covered  if n_results > 0 else None,
        "all_12_correct": int(correct_picks == 12 and n_results == 12),
        "hit_rate":       round(correct_picks / n_results, 4) if n_results > 0 else None,
        "cover_rate":     round(system_covered / n_results, 4) if n_results > 0 else None,
        "evaluation_status": status,
        "n_results":      n_results,
    }


def save_evaluation(coupon_id: str, total_rows: int, stake_nok: float) -> dict:
    """Compute and persist a coupon evaluation. Returns the evaluation dict."""
    ev = compute_evaluation(coupon_id, total_rows, stake_nok)
    if ev.get("evaluation_status") == "pending":
        return ev

    ev_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO coupon_evaluations
               (evaluation_id, coupon_id, total_rows, stake_nok, total_fixtures,
                correct_picks, system_covered, all_12_correct,
                hit_rate, cover_rate, evaluation_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(coupon_id) DO UPDATE SET
                   total_rows        = excluded.total_rows,
                   stake_nok         = excluded.stake_nok,
                   total_fixtures    = excluded.total_fixtures,
                   correct_picks     = excluded.correct_picks,
                   system_covered    = excluded.system_covered,
                   all_12_correct    = excluded.all_12_correct,
                   hit_rate          = excluded.hit_rate,
                   cover_rate        = excluded.cover_rate,
                   evaluation_status = excluded.evaluation_status,
                   evaluated_at      = datetime('now')""",
            (ev_id, coupon_id, total_rows, stake_nok, ev["total_fixtures"],
             ev["correct_picks"], ev["system_covered"], ev["all_12_correct"],
             ev["hit_rate"], ev["cover_rate"], ev["evaluation_status"]),
        )
    return ev


def get_evaluation(coupon_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM coupon_evaluations WHERE coupon_id=?", (coupon_id,)
        ).fetchone()
    return dict(row) if row else None


def list_evaluated_coupons(limit: int = 100) -> list[dict]:
    """Return all coupons with evaluations, joined to coupon metadata, newest first."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.*, c.week, c.year, c.day_type, c.label, c.deadline_utc
               FROM coupon_evaluations e
               JOIN coupons c ON c.coupon_id = e.coupon_id
               ORDER BY c.deadline_utc DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_coupons_with_predictions(limit: int = 100) -> list[dict]:
    """
    Return all coupons that have predictions saved, with result counts.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   c.coupon_id, c.week, c.year, c.day_type, c.label, c.deadline_utc,
                   COUNT(DISTINCT p.fixture_id) AS n_predictions,
                   COUNT(DISTINCT r.fixture_id) AS n_results
               FROM coupons c
               JOIN coupon_predictions p ON p.coupon_id = c.coupon_id
               LEFT JOIN match_results r ON r.fixture_id = p.fixture_id
               GROUP BY c.coupon_id
               ORDER BY c.deadline_utc DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Coupon save snapshot (Phase 8) ───────────────────────────────────────────────

def save_coupon_snapshot(
    coupon_id: str,
    strategy: str,
    budget_nok: float,
    total_rows: int,
    p_win: float | None = None,
    pvr: float | None = None,
) -> None:
    """Upsert coupon-level save metadata. Latest save always wins."""
    snap_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO coupon_save_snapshot
               (snapshot_id, coupon_id, strategy, budget_nok, total_rows, p_win, pvr)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(coupon_id) DO UPDATE SET
                   strategy   = excluded.strategy,
                   budget_nok = excluded.budget_nok,
                   total_rows = excluded.total_rows,
                   p_win      = excluded.p_win,
                   pvr        = excluded.pvr,
                   saved_at   = datetime('now')""",
            (snap_id, coupon_id, strategy, budget_nok, total_rows, p_win, pvr),
        )


def get_coupon_snapshot(coupon_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM coupon_save_snapshot WHERE coupon_id=?", (coupon_id,)
        ).fetchone()
    return dict(row) if row else None
