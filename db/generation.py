"""
Phase 9 — generation-based historical tracking.

Every call to POST /v1/optimize auto-saves a live generation record (one per
coupon + strategy + budget per calendar day, last write wins).

Before deadline, freeze_coupon_combo() promotes a live record to frozen (or
creates a new frozen record). Frozen records are never overwritten. Analytics
only use frozen/evaluated generations.

Public API:
    upsert_generation(...)             -> str | None   (generation_id)
    freeze_coupon_combo(...)           -> dict | None
    evaluate_generation(gen_id)        -> dict
    sweep_pending_evaluations()        -> list[dict]
    get_strategy_analytics()           -> list[dict]
"""
from __future__ import annotations

import json
import uuid
from db.connection import get_conn


# ── Upsert (live only) ────────────────────────────────────────────────────────

def upsert_generation(
    coupon_id: str,
    strategy: str,
    budget: float,
    row_count: int,
    p_win: float | None,
    pvr: float | None,
    n_singles: int,
    n_halvdekk: int,
    n_heldekk: int,
    coverage_dist: dict[int, int],
    picks_data: list[dict],
) -> str | None:
    """
    Insert or update a live generation record for (coupon_id, strategy, budget, today).

    If a frozen or evaluated record already exists for this combo, returns its
    generation_id without making any changes — frozen records are never overwritten.

    Returns the generation_id, or None if storage fails or no picks have fixture_ids.
    """
    if not any(p.get("fixture_id") for p in picks_data):
        return None

    with get_conn() as conn:
        # Never overwrite a frozen/evaluated record
        frozen = conn.execute(
            """SELECT generation_id FROM coupon_generations
               WHERE coupon_id=? AND strategy=? AND budget=?
                 AND status IN ('frozen','evaluated')""",
            (coupon_id, strategy, budget),
        ).fetchone()
        if frozen:
            return frozen["generation_id"]

        row = conn.execute(
            """SELECT generation_id FROM coupon_generations
               WHERE coupon_id=? AND strategy=? AND budget=?
                 AND date(generated_at)=date('now')
                 AND status='live'""",
            (coupon_id, strategy, budget),
        ).fetchone()

        if row:
            gen_id = row["generation_id"]
            conn.execute(
                """UPDATE coupon_generations SET
                       row_count=?, p_win=?, pvr=?,
                       n_singles=?, n_halvdekk=?, n_heldekk=?,
                       fixtures_4of4=?, fixtures_3of4=?, fixtures_2of4=?,
                       fixtures_1of4=?, fixtures_0of4=?,
                       generated_at=datetime('now')
                   WHERE generation_id=?""",
                (row_count, p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                 coverage_dist.get(4, 0), coverage_dist.get(3, 0),
                 coverage_dist.get(2, 0), coverage_dist.get(1, 0),
                 coverage_dist.get(0, 0), gen_id),
            )
            conn.execute(
                "DELETE FROM generation_picks WHERE generation_id=?", (gen_id,)
            )
        else:
            gen_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO coupon_generations
                   (generation_id, coupon_id, strategy, budget, row_count,
                    p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                    fixtures_4of4, fixtures_3of4, fixtures_2of4, fixtures_1of4, fixtures_0of4,
                    status)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'live')""",
                (gen_id, coupon_id, strategy, budget, row_count,
                 p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                 coverage_dist.get(4, 0), coverage_dist.get(3, 0),
                 coverage_dist.get(2, 0), coverage_dist.get(1, 0),
                 coverage_dist.get(0, 0)),
            )

        _insert_picks(conn, gen_id, picks_data)

    return gen_id


# ── Freeze ────────────────────────────────────────────────────────────────────

def freeze_coupon_combo(
    coupon_id: str,
    strategy: str,
    budget: float,
    row_count: int,
    p_win: float | None,
    pvr: float | None,
    n_singles: int,
    n_halvdekk: int,
    n_heldekk: int,
    coverage_dist: dict[int, int],
    picks_data: list[dict],
) -> dict | None:
    """
    Freeze one (coupon, strategy, budget) combo with the current model output.

    Actions:
      - already_frozen : frozen/evaluated record exists — no change, returns its id
      - upgraded       : existing live record promoted to frozen with fresh picks
      - created        : no prior record — new frozen record inserted

    Returns {"generation_id": str, "action": str} or None if no fixture_ids.
    """
    if not any(p.get("fixture_id") for p in picks_data):
        return None

    with get_conn() as conn:
        existing = conn.execute(
            """SELECT generation_id FROM coupon_generations
               WHERE coupon_id=? AND strategy=? AND budget=?
                 AND status IN ('frozen','evaluated')""",
            (coupon_id, strategy, budget),
        ).fetchone()
        if existing:
            return {"generation_id": existing["generation_id"], "action": "already_frozen"}

        live = conn.execute(
            """SELECT generation_id FROM coupon_generations
               WHERE coupon_id=? AND strategy=? AND budget=?
                 AND status='live'
               ORDER BY generated_at DESC LIMIT 1""",
            (coupon_id, strategy, budget),
        ).fetchone()

        if live:
            gen_id = live["generation_id"]
            conn.execute(
                """UPDATE coupon_generations SET
                       status='frozen', frozen_at=datetime('now'),
                       row_count=?, p_win=?, pvr=?,
                       n_singles=?, n_halvdekk=?, n_heldekk=?,
                       fixtures_4of4=?, fixtures_3of4=?, fixtures_2of4=?,
                       fixtures_1of4=?, fixtures_0of4=?,
                       generated_at=datetime('now')
                   WHERE generation_id=?""",
                (row_count, p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                 coverage_dist.get(4, 0), coverage_dist.get(3, 0),
                 coverage_dist.get(2, 0), coverage_dist.get(1, 0),
                 coverage_dist.get(0, 0), gen_id),
            )
            conn.execute("DELETE FROM generation_picks WHERE generation_id=?", (gen_id,))
            action = "upgraded"
        else:
            gen_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO coupon_generations
                   (generation_id, coupon_id, strategy, budget, row_count,
                    p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                    fixtures_4of4, fixtures_3of4, fixtures_2of4, fixtures_1of4, fixtures_0of4,
                    status, frozen_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'frozen',datetime('now'))""",
                (gen_id, coupon_id, strategy, budget, row_count,
                 p_win, pvr, n_singles, n_halvdekk, n_heldekk,
                 coverage_dist.get(4, 0), coverage_dist.get(3, 0),
                 coverage_dist.get(2, 0), coverage_dist.get(1, 0),
                 coverage_dist.get(0, 0)),
            )
            action = "created"

        _insert_picks(conn, gen_id, picks_data)

    return {"generation_id": gen_id, "action": action}


# ── Shared pick insertion ─────────────────────────────────────────────────────

def _insert_picks(conn, gen_id: str, picks_data: list[dict]) -> None:
    for p in picks_data:
        if not p.get("fixture_id"):
            continue
        conn.execute(
            """INSERT INTO generation_picks
               (pick_id, generation_id, fixture_id, match_number,
                pick, coverage_type, selected_outcomes, confidence,
                model_prob_h, model_prob_u, model_prob_b,
                pub_prob_h, pub_prob_u, pub_prob_b,
                value_h, value_u, value_b,
                crowd_disagreement_score, odds_source, has_af_data)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), gen_id, p["fixture_id"], p["match_number"],
             p["pick"], p["coverage_type"],
             json.dumps(p.get("selected_outcomes", [])),
             p["confidence"],
             p.get("model_prob_h"), p.get("model_prob_u"), p.get("model_prob_b"),
             p.get("pub_prob_h"), p.get("pub_prob_u"), p.get("pub_prob_b"),
             p.get("value_h"), p.get("value_u"), p.get("value_b"),
             p.get("crowd_disagreement_score"), p.get("odds_source"),
             int(bool(p.get("has_af_data", 0)))),
        )


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_generation(generation_id: str) -> dict:
    """
    Evaluate one generation against match_results and persist to generation_results.
    Idempotent — safe to call repeatedly as results arrive.

    When evaluation is complete, promotes frozen → evaluated in coupon_generations.
    """
    with get_conn() as conn:
        picks = conn.execute(
            """SELECT gp.fixture_id, gp.match_number, gp.pick,
                      gp.coverage_type, gp.selected_outcomes,
                      r.result_1x2
               FROM generation_picks gp
               LEFT JOIN match_results r ON r.fixture_id = gp.fixture_id
               WHERE gp.generation_id = ?
               ORDER BY gp.match_number""",
            (generation_id,),
        ).fetchall()

    if not picks:
        return {"generation_id": generation_id, "evaluation_status": "no_picks"}

    n_total = len(picks)
    has_result = [p for p in picks if p["result_1x2"] is not None]
    n_results = len(has_result)

    if n_results == 0:
        status = "pending"
        correct_picks = None
        covered_picks = None
        all_correct = 0
    else:
        # correct_picks: a match is correct when the coupon covered the actual result
        covered = 0
        for p in has_result:
            try:
                selected = json.loads(p["selected_outcomes"])
            except Exception:
                selected = [p["pick"]]
            if p["result_1x2"] in selected:
                covered += 1
        correct_picks = covered

        # covered_picks: primary model pick accuracy — internal diagnostic only
        covered_picks = sum(1 for p in has_result if p["pick"] == p["result_1x2"])

        all_correct = int(n_results == n_total and correct_picks == n_total)
        status = "complete" if n_results == n_total else "partial"

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO generation_results
               (generation_id, correct_picks, covered_picks, all_correct, evaluation_status)
               VALUES (?,?,?,?,?)
               ON CONFLICT(generation_id) DO UPDATE SET
                   correct_picks     = excluded.correct_picks,
                   covered_picks     = excluded.covered_picks,
                   all_correct       = excluded.all_correct,
                   evaluation_status = excluded.evaluation_status,
                   evaluated_at      = datetime('now')""",
            (generation_id, correct_picks, covered_picks, all_correct, status),
        )
        # Promote frozen → evaluated when all results are known
        if status == "complete":
            conn.execute(
                """UPDATE coupon_generations SET status='evaluated'
                   WHERE generation_id=? AND status='frozen'""",
                (generation_id,),
            )

    return {
        "generation_id":     generation_id,
        "evaluation_status": status,
        "correct_picks":     correct_picks,
        "covered_picks":     covered_picks,
        "all_correct":       all_correct,
    }


def sweep_pending_evaluations() -> list[dict]:
    """Evaluate frozen/evaluated generations that have no result or are pending/partial."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT g.generation_id
               FROM coupon_generations g
               LEFT JOIN generation_results r ON r.generation_id = g.generation_id
               WHERE g.status IN ('frozen', 'evaluated')
                 AND (r.generation_id IS NULL
                      OR r.evaluation_status IN ('pending', 'partial'))""",
        ).fetchall()

    results = []
    for row in rows:
        result = evaluate_generation(row["generation_id"])
        results.append(result)
    return results


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_all_generations_summary() -> list[dict]:
    """
    All frozen/evaluated generations with coupon metadata and evaluation summary.
    Ordered newest coupon first, then safe → balanced → jackpot, then budget ascending.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   cg.generation_id,
                   cg.coupon_id,
                   cg.strategy,
                   CAST(cg.budget AS REAL)               AS budget,
                   cg.row_count,
                   cg.p_win,
                   cg.pvr,
                   cg.n_singles,
                   cg.n_halvdekk,
                   cg.n_heldekk,
                   cg.frozen_at,
                   cg.status,
                   COALESCE(gr.evaluation_status,'pending') AS evaluation_status,
                   gr.correct_picks,
                   COALESCE(gr.all_correct, 0)            AS all_correct,
                   gr.actual_payout_nok,
                   gr.evaluated_at,
                   c.label        AS coupon_label,
                   c.week,
                   c.year,
                   c.day_type,
                   c.deadline_utc
               FROM coupon_generations cg
               JOIN coupons c ON c.coupon_id = cg.coupon_id
               LEFT JOIN generation_results gr ON gr.generation_id = cg.generation_id
               WHERE cg.status IN ('frozen', 'evaluated')
               ORDER BY c.deadline_utc DESC,
                   CASE cg.strategy
                       WHEN 'safe'     THEN 1
                       WHEN 'balanced' THEN 2
                       WHEN 'jackpot'  THEN 3
                       ELSE 4 END,
                   cg.budget""",
        ).fetchall()
    return [dict(r) for r in rows]


def get_generation_detail(generation_id: str) -> dict | None:
    """
    Full generation: metadata + all picks with team names and actual results.
    Picks are ordered by match_number. `covered` is derived at read time.
    """
    with get_conn() as conn:
        meta = conn.execute(
            """SELECT
                   cg.generation_id, cg.coupon_id, cg.strategy,
                   CAST(cg.budget AS REAL) AS budget,
                   cg.row_count, cg.p_win, cg.pvr,
                   cg.n_singles, cg.n_halvdekk, cg.n_heldekk,
                   cg.frozen_at, cg.status,
                   COALESCE(gr.evaluation_status,'pending') AS evaluation_status,
                   gr.correct_picks,
                   COALESCE(gr.all_correct, 0) AS all_correct,
                   gr.actual_payout_nok,
                   gr.evaluated_at,
                   c.label AS coupon_label, c.week, c.year,
                   c.day_type, c.deadline_utc
               FROM coupon_generations cg
               JOIN coupons c ON c.coupon_id = cg.coupon_id
               LEFT JOIN generation_results gr ON gr.generation_id = cg.generation_id
               WHERE cg.generation_id = ?""",
            (generation_id,),
        ).fetchone()

        if not meta:
            return None

        picks = conn.execute(
            """SELECT
                   gp.match_number,
                   gp.fixture_id,
                   gp.pick,
                   gp.coverage_type,
                   gp.selected_outcomes,
                   gp.confidence,
                   COALESCE(th.name_local, th.name_canonical) AS home_name,
                   COALESCE(ta.name_local, ta.name_canonical) AS away_name,
                   mr.result_1x2,
                   mr.home_score,
                   mr.away_score
               FROM generation_picks gp
               JOIN fixtures f ON f.fixture_id  = gp.fixture_id
               JOIN teams th   ON th.team_id    = f.home_team_id
               JOIN teams ta   ON ta.team_id    = f.away_team_id
               LEFT JOIN match_results mr ON mr.fixture_id = gp.fixture_id
               WHERE gp.generation_id = ?
               ORDER BY gp.match_number""",
            (generation_id,),
        ).fetchall()

    result = dict(meta)
    pick_list = []
    for p in picks:
        pd = dict(p)
        try:
            selected = json.loads(pd["selected_outcomes"])
        except Exception:
            selected = [pd["pick"]]
        pd["selected_outcomes"] = selected
        if pd.get("result_1x2") is not None:
            pd["covered"] = pd["result_1x2"] in selected
        else:
            pd["covered"] = None
        pick_list.append(pd)

    result["picks"] = pick_list
    result["n_total"] = len(pick_list)
    result["n_evaluated"] = sum(1 for p in pick_list if p.get("result_1x2") is not None)
    return result


def get_calibration_picks() -> list[dict]:
    """
    Return all picks from frozen/evaluated generations that have a known result.

    Each row is a dict with all generation_picks columns plus:
        strategy, budget         — from coupon_generations
        result_1x2               — actual outcome
        pick_hit   (int 0/1)     — model primary pick == result
        coverage_hit (int 0/1)   — result in selected_outcomes (coupon covered it)
        vi         (float|None)  — model_prob_pick / pub_prob_pick
        model_prob_pick (float)  — model prob for the recommended pick
        pub_prob_pick   (float)  — public prob for the recommended pick
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   cg.generation_id, cg.strategy, CAST(cg.budget AS REAL) AS budget,
                   gp.match_number, gp.fixture_id,
                   gp.pick, gp.coverage_type, gp.selected_outcomes, gp.confidence,
                   gp.model_prob_h, gp.model_prob_u, gp.model_prob_b,
                   gp.pub_prob_h, gp.pub_prob_u, gp.pub_prob_b,
                   gp.value_h, gp.value_u, gp.value_b,
                   gp.crowd_disagreement_score,
                   mr.result_1x2
               FROM generation_picks gp
               JOIN coupon_generations cg ON cg.generation_id = gp.generation_id
               JOIN match_results mr ON mr.fixture_id = gp.fixture_id
               WHERE cg.status IN ('frozen', 'evaluated')
                 AND mr.result_1x2 IS NOT NULL
               ORDER BY cg.strategy, cg.budget, gp.match_number""",
        ).fetchall()

    picks = []
    for r in rows:
        d = dict(r)
        result = d["result_1x2"]
        pick = d["pick"]

        try:
            selected = json.loads(d["selected_outcomes"])
        except Exception:
            selected = [pick]
        d["selected_outcomes"] = selected

        d["pick_hit"] = int(pick == result)
        d["coverage_hit"] = int(result in selected)

        mp_map = {
            "H": d.get("model_prob_h"),
            "U": d.get("model_prob_u"),
            "B": d.get("model_prob_b"),
        }
        pp_map = {
            "H": d.get("pub_prob_h"),
            "U": d.get("pub_prob_u"),
            "B": d.get("pub_prob_b"),
        }
        mp = mp_map.get(pick)
        pp = pp_map.get(pick)
        d["model_prob_pick"] = mp
        d["pub_prob_pick"] = pp
        d["vi"] = (mp / pp) if (mp and pp and pp > 0) else None

        picks.append(d)

    return picks


def get_strategy_analytics() -> list[dict]:
    """
    Per-strategy summary over frozen and evaluated generations only.

    Hit rates (hit_rate_9 … hit_rate_12) are percentages (0–100).
    Only complete evaluations (all 12 results known) are counted for hit rates and avg_hits.
    avg_pvr and avg_p_win are over all frozen/evaluated generations.
    roi requires actual_payout_nok to be filled in post-win; returns NULL until then.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   g.strategy,
                   COUNT(DISTINCT g.generation_id)  AS n_total,
                   COUNT(DISTINCT CASE WHEN r.evaluation_status = 'complete'
                         THEN g.generation_id END)  AS n_evaluated,
                   AVG(CASE WHEN r.evaluation_status = 'complete'
                       THEN r.correct_picks END)     AS avg_hits,
                   AVG(g.pvr)                        AS avg_pvr,
                   AVG(g.p_win)                      AS avg_p_win,
                   100.0 * SUM(CASE WHEN r.evaluation_status='complete'
                               AND r.correct_picks >= 9  THEN 1 ELSE 0 END) /
                       NULLIF(SUM(CASE WHEN r.evaluation_status='complete'
                                  THEN 1 ELSE 0 END), 0)  AS hit_rate_9,
                   100.0 * SUM(CASE WHEN r.evaluation_status='complete'
                               AND r.correct_picks >= 10 THEN 1 ELSE 0 END) /
                       NULLIF(SUM(CASE WHEN r.evaluation_status='complete'
                                  THEN 1 ELSE 0 END), 0)  AS hit_rate_10,
                   100.0 * SUM(CASE WHEN r.evaluation_status='complete'
                               AND r.correct_picks >= 11 THEN 1 ELSE 0 END) /
                       NULLIF(SUM(CASE WHEN r.evaluation_status='complete'
                                  THEN 1 ELSE 0 END), 0)  AS hit_rate_11,
                   100.0 * SUM(CASE WHEN r.evaluation_status='complete'
                               AND r.correct_picks = 12  THEN 1 ELSE 0 END) /
                       NULLIF(SUM(CASE WHEN r.evaluation_status='complete'
                                  THEN 1 ELSE 0 END), 0)  AS hit_rate_12,
                   CASE WHEN SUM(CASE WHEN r.evaluation_status='complete'
                                THEN g.budget END) > 0
                       THEN (SUM(CASE WHEN r.evaluation_status='complete'
                                 THEN COALESCE(r.actual_payout_nok, 0) END) -
                             SUM(CASE WHEN r.evaluation_status='complete'
                                 THEN g.budget END)) /
                            SUM(CASE WHEN r.evaluation_status='complete'
                                THEN g.budget END)
                       ELSE NULL END                  AS roi
               FROM coupon_generations g
               LEFT JOIN generation_results r ON r.generation_id = g.generation_id
               WHERE g.status IN ('frozen', 'evaluated')
               GROUP BY g.strategy
               ORDER BY CASE g.strategy
                   WHEN 'safe'     THEN 1
                   WHEN 'balanced' THEN 2
                   WHEN 'jackpot'  THEN 3
                   ELSE 4 END""",
        ).fetchall()
    return [dict(r) for r in rows]
