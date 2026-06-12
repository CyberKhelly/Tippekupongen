"""
Phase 8 — Automated coupon evaluation pipeline.

evaluate_coupon(coupon_id) is the primary entry point:
  - Reads ONLY saved snapshot fields from coupon_predictions (frozen at save time).
  - Never reads live coupon_fixtures.public_h/u/b.
  - For old coupons where pub_prob_*/value_*/cds are NULL, nt_correct/vi_bucket/edge_pp
    are NULL; model hit rate and coverage are still computed.
  - Idempotent: re-running updates existing rows.

Query helpers for History page:
  get_pick_evaluations(coupon_id)
  get_strategy_performance()
  get_cds_validation()
  get_conviction_stats()
  get_nt_model_comparison()
  get_pvr_payout_data()
"""
from __future__ import annotations
import json
import uuid
from db.connection import get_conn


# ── Bucket helpers ────────────────────────────────────────────────────────────

def _cds_bucket(cds: float | None) -> str | None:
    if cds is None:
        return None
    if cds >= 10:
        return "high"
    if cds >= 5:
        return "medium"
    return "low"


def _vi_bucket(vi: float | None) -> str | None:
    if vi is None:
        return None
    if vi >= 1.5:
        return "strong"
    if vi >= 1.25:
        return "good"
    if vi >= 0.9:
        return "neutral"
    return "weak"


def _edge_bucket(edge_pp: float | None) -> str | None:
    if edge_pp is None:
        return None
    if edge_pp > 5:
        return "under"   # crowd underplays our pick — positive edge
    if edge_pp < -5:
        return "over"    # crowd overplays our pick — negative edge
    return "neutral"


# ── Core evaluation ───────────────────────────────────────────────────────────

def evaluate_coupon(coupon_id: str) -> dict:
    """
    Compute and persist pick_evaluations + coupon_evaluations for one coupon.

    Uses only columns from coupon_predictions (frozen at save time).
    Snapshot fields (pub_prob_*, value_*, crowd_disagreement_score) are NULL
    for coupons saved before Phase 8 — those rows degrade gracefully.

    Returns a summary dict with evaluation_status and key metrics.
    """
    with get_conn() as conn:
        pred_rows = conn.execute(
            """SELECT p.match_number, p.fixture_id,
                      p.recommended_pick, p.coverage_type, p.selected_outcomes,
                      p.confidence,
                      p.implied_prob_h, p.implied_prob_u, p.implied_prob_b,
                      p.pub_prob_h, p.pub_prob_u, p.pub_prob_b,
                      p.value_h, p.value_u, p.value_b,
                      p.crowd_disagreement_score,
                      r.result_1x2
               FROM coupon_predictions p
               LEFT JOIN match_results r ON r.fixture_id = p.fixture_id
               WHERE p.coupon_id = ?
               ORDER BY p.match_number""",
            (coupon_id,),
        ).fetchall()

        snap_row = conn.execute(
            "SELECT * FROM coupon_save_snapshot WHERE coupon_id = ?",
            (coupon_id,),
        ).fetchone()

    if not pred_rows:
        return {"evaluation_status": "no_predictions", "coupon_id": coupon_id}

    snap = dict(snap_row) if snap_row else {}
    pick_evals: list[dict] = []

    for row in pred_rows:
        r = dict(row)
        result   = r.get("result_1x2")
        rec      = r["recommended_pick"]
        cov_type = r["coverage_type"]

        try:
            selected = json.loads(r["selected_outcomes"])
        except Exception:
            selected = []

        # ── Coverage and model correctness ────────────────────────────────────
        covered = model_correct = nt_correct = None
        if result:
            covered       = int(result in selected)
            model_correct = int(rec == result)

            ph = r.get("pub_prob_h")
            pu = r.get("pub_prob_u")
            pb = r.get("pub_prob_b")
            if ph is not None and pu is not None and pb is not None:
                tot = (ph or 0.0) + (pu or 0.0) + (pb or 0.0)
                if tot > 0.01:
                    nt_pick = max(
                        {"H": ph / tot, "U": pu / tot, "B": pb / tot},
                        key=lambda k, d={"H": ph/tot, "U": pu/tot, "B": pb/tot}: d[k],
                    )
                    nt_correct = int(nt_pick == result)

        # ── CDS bucket ────────────────────────────────────────────────────────
        cds    = r.get("crowd_disagreement_score")
        cds_bk = _cds_bucket(cds)

        # ── Value index of recommended pick ───────────────────────────────────
        val_map = {"H": r.get("value_h"), "U": r.get("value_u"), "B": r.get("value_b")}
        value_rec = val_map.get(rec)

        # VI = model_prob / pub_prob; reconstruct pub_prob from stored value (pp diff)
        vi_val: float | None = None
        ph = r.get("pub_prob_h")
        pu = r.get("pub_prob_u")
        pb = r.get("pub_prob_b")
        if ph is not None and pu is not None and pb is not None:
            tot = (ph or 0.0) + (pu or 0.0) + (pb or 0.0)
            if tot > 0.01:
                pub_rec = {"H": ph / tot, "U": pu / tot, "B": pb / tot}.get(rec, 0.0)
                imp_rec = r.get(f"implied_prob_{rec.lower()}", 0.0) or 0.0
                if pub_rec >= 0.02:
                    vi_val = min(5.0, round(imp_rec / pub_rec, 3))
        vi_bk = _vi_bucket(vi_val)

        # ── Edge pp — model minus public on recommended pick ──────────────────
        edge_pp: float | None = None
        if ph is not None and pu is not None and pb is not None:
            tot = (ph or 0.0) + (pu or 0.0) + (pb or 0.0)
            if tot > 0.01:
                pub_rec = {"H": ph / tot, "U": pu / tot, "B": pb / tot}.get(rec, 0.0)
                imp_rec = r.get(f"implied_prob_{rec.lower()}", 0.0) or 0.0
                edge_pp = round((imp_rec - pub_rec) * 100, 2)
        edge_bk = _edge_bucket(edge_pp)

        # ── Conviction: single pick with high confidence ──────────────────────
        is_conviction = int(cov_type == "single" and (r.get("confidence") or 0.0) >= 0.55)

        pick_evals.append({
            "pick_eval_id": str(uuid.uuid4()),
            "coupon_id":    coupon_id,
            "fixture_id":   r["fixture_id"],
            "match_number": r["match_number"],
            "result_1x2":   result,
            "covered":      covered,
            "model_correct":model_correct,
            "nt_correct":   nt_correct,
            "cds":          cds,
            "cds_bucket":   cds_bk,
            "value_rec":    value_rec,
            "vi_bucket":    vi_bk,
            "edge_pp":      edge_pp,
            "edge_bucket":  edge_bk,
            "coverage_type":cov_type,
            "is_conviction":is_conviction,
        })

    # ── Persist pick_evaluations ──────────────────────────────────────────────
    with get_conn() as conn:
        for pe in pick_evals:
            conn.execute(
                """INSERT INTO pick_evaluations
                   (pick_eval_id, coupon_id, fixture_id, match_number,
                    result_1x2, covered, model_correct, nt_correct,
                    cds, cds_bucket, value_rec, vi_bucket,
                    edge_pp, edge_bucket, coverage_type, is_conviction)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(coupon_id, fixture_id) DO UPDATE SET
                       result_1x2    = excluded.result_1x2,
                       covered       = excluded.covered,
                       model_correct = excluded.model_correct,
                       nt_correct    = excluded.nt_correct,
                       cds           = excluded.cds,
                       cds_bucket    = excluded.cds_bucket,
                       value_rec     = excluded.value_rec,
                       vi_bucket     = excluded.vi_bucket,
                       edge_pp       = excluded.edge_pp,
                       edge_bucket   = excluded.edge_bucket,
                       coverage_type = excluded.coverage_type,
                       is_conviction = excluded.is_conviction,
                       evaluated_at  = datetime('now')""",
                (pe["pick_eval_id"], pe["coupon_id"], pe["fixture_id"], pe["match_number"],
                 pe["result_1x2"], pe["covered"], pe["model_correct"], pe["nt_correct"],
                 pe["cds"], pe["cds_bucket"], pe["value_rec"], pe["vi_bucket"],
                 pe["edge_pp"], pe["edge_bucket"], pe["coverage_type"], pe["is_conviction"]),
            )

    # ── Aggregate metrics ─────────────────────────────────────────────────────
    has_result  = [pe for pe in pick_evals if pe["result_1x2"] is not None]
    n_results   = len(has_result)
    n_total     = len(pick_evals)

    correct_picks  = sum(pe["model_correct"] or 0 for pe in has_result)
    system_covered = sum(pe["covered"]       or 0 for pe in has_result)

    nt_avail   = [pe for pe in has_result if pe["nt_correct"] is not None]
    n_nt_corr  = sum(pe["nt_correct"] for pe in nt_avail)

    if n_results == 0:
        status = "pending"
    elif n_results < n_total:
        status = "partial"
    else:
        status = "complete"

    ev_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO coupon_evaluations
               (evaluation_id, coupon_id, total_rows, stake_nok, total_fixtures,
                correct_picks, system_covered, all_12_correct,
                hit_rate, cover_rate, evaluation_status,
                strategy, budget_nok, pvr_at_save, p_win_at_save,
                n_nt_correct, nt_hit_rate, n_matches_evaluated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(coupon_id) DO UPDATE SET
                   total_rows          = excluded.total_rows,
                   stake_nok           = excluded.stake_nok,
                   total_fixtures      = excluded.total_fixtures,
                   correct_picks       = excluded.correct_picks,
                   system_covered      = excluded.system_covered,
                   all_12_correct      = excluded.all_12_correct,
                   hit_rate            = excluded.hit_rate,
                   cover_rate          = excluded.cover_rate,
                   evaluation_status   = excluded.evaluation_status,
                   strategy            = excluded.strategy,
                   budget_nok          = excluded.budget_nok,
                   pvr_at_save         = excluded.pvr_at_save,
                   p_win_at_save       = excluded.p_win_at_save,
                   n_nt_correct        = excluded.n_nt_correct,
                   nt_hit_rate         = excluded.nt_hit_rate,
                   n_matches_evaluated = excluded.n_matches_evaluated,
                   evaluated_at        = datetime('now')""",
            (ev_id, coupon_id,
             snap.get("total_rows", 0), snap.get("budget_nok", 0), n_total,
             correct_picks  if n_results > 0 else None,
             system_covered if n_results > 0 else None,
             int(correct_picks == 12 and n_results == 12),
             round(correct_picks  / n_results, 4) if n_results > 0 else None,
             round(system_covered / n_results, 4) if n_results > 0 else None,
             status,
             snap.get("strategy"),
             snap.get("budget_nok"),
             snap.get("pvr"),
             snap.get("p_win"),
             n_nt_corr  if nt_avail else None,
             round(n_nt_corr / len(nt_avail), 4) if nt_avail else None,
             n_results),
        )

    return {
        "coupon_id":         coupon_id,
        "evaluation_status": status,
        "n_total":           n_total,
        "n_results":         n_results,
        "correct_picks":     correct_picks  if n_results > 0 else None,
        "system_covered":    system_covered if n_results > 0 else None,
        "hit_rate":          round(correct_picks  / n_results, 4) if n_results > 0 else None,
        "cover_rate":        round(system_covered / n_results, 4) if n_results > 0 else None,
        "n_nt_correct":      n_nt_corr if nt_avail else None,
        "n_nt_avail":        len(nt_avail),
        "strategy":          snap.get("strategy"),
        "pvr_at_save":       snap.get("pvr"),
        "budget_nok":        snap.get("budget_nok"),
    }


# ── Query helpers for History page ───────────────────────────────────────────

def get_pick_evaluations(coupon_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT pe.*,
                      COALESCE(th.name_local, th.name_canonical) AS home_name,
                      COALESCE(ta.name_local, ta.name_canonical) AS away_name
               FROM pick_evaluations pe
               JOIN fixtures f ON f.fixture_id = pe.fixture_id
               JOIN teams th   ON th.team_id   = f.home_team_id
               JOIN teams ta   ON ta.team_id   = f.away_team_id
               WHERE pe.coupon_id = ?
               ORDER BY pe.match_number""",
            (coupon_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_strategy_performance() -> list[dict]:
    """Aggregate by strategy across all evaluated coupons."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   e.strategy,
                   COUNT(*) AS n_coupons,
                   AVG(e.hit_rate)         AS avg_hit_rate,
                   AVG(e.cover_rate)       AS avg_cover_rate,
                   SUM(e.all_12_correct)   AS n_jackpots,
                   AVG(s.pvr)              AS avg_pvr,
                   AVG(s.p_win)            AS avg_p_win,
                   AVG(e.nt_hit_rate)      AS avg_nt_hit_rate
               FROM coupon_evaluations e
               LEFT JOIN coupon_save_snapshot s ON s.coupon_id = e.coupon_id
               WHERE e.evaluation_status IN ('complete','partial')
                 AND e.strategy IS NOT NULL
               GROUP BY e.strategy
               ORDER BY e.strategy""",
        ).fetchall()
    return [dict(r) for r in rows]


def get_cds_validation() -> list[dict]:
    """
    CDS bucket accuracy from saved pick_evaluations (frozen at prediction time).
    Only includes rows where cds is not NULL (Phase 8+ saves).
    Excludes rows without a result.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   cds_bucket,
                   COUNT(*)             AS n,
                   SUM(model_correct)   AS n_model,
                   SUM(nt_correct)      AS n_nt
               FROM pick_evaluations
               WHERE result_1x2 IS NOT NULL
                 AND cds_bucket IS NOT NULL
                 AND cds IS NOT NULL
               GROUP BY cds_bucket
               ORDER BY CASE cds_bucket
                   WHEN 'high'   THEN 1
                   WHEN 'medium' THEN 2
                   WHEN 'low'    THEN 3
                   ELSE 4 END""",
        ).fetchall()
    return [dict(r) for r in rows]


def get_conviction_stats() -> list[dict]:
    """
    Hit rate and cover rate split by is_conviction and coverage_type.
    Only includes rows with a result.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   is_conviction,
                   coverage_type,
                   COUNT(*)           AS n,
                   SUM(model_correct) AS n_correct,
                   SUM(covered)       AS n_covered
               FROM pick_evaluations
               WHERE result_1x2 IS NOT NULL
               GROUP BY is_conviction, coverage_type
               ORDER BY coverage_type, is_conviction DESC""",
        ).fetchall()
    return [dict(r) for r in rows]


def get_nt_model_comparison() -> dict:
    """
    Overall model vs NT public accuracy across all evaluated picks with snapshot data.
    """
    with get_conn() as conn:
        row = conn.execute(
            """SELECT
                   COUNT(*)             AS n_total,
                   SUM(model_correct)   AS n_model,
                   SUM(nt_correct)      AS n_nt
               FROM pick_evaluations
               WHERE result_1x2 IS NOT NULL
                 AND nt_correct IS NOT NULL""",
        ).fetchone()
    return dict(row) if row else {}


def get_pvr_payout_data() -> list[dict]:
    """PVR at save time vs actual payout (only rows where actual_payout_nok is set)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   s.pvr,
                   e.actual_payout_nok,
                   e.hit_rate,
                   e.cover_rate,
                   c.week,
                   c.year,
                   e.strategy
               FROM coupon_save_snapshot s
               JOIN coupon_evaluations e ON e.coupon_id = s.coupon_id
               JOIN coupons c            ON c.coupon_id  = s.coupon_id
               WHERE e.actual_payout_nok IS NOT NULL
               ORDER BY c.deadline_utc DESC""",
        ).fetchall()
    return [dict(r) for r in rows]
