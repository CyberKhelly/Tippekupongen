"""
Phase 15 — User-saved coupon snapshots.

Distinct from Phase 9 (auto-generated optimizer state) and Phase 8A (legacy).

A saved snapshot is created when the user explicitly clicks "Lagre kupong".
Multiple snapshots per (coupon_id, strategy, budget) are allowed — the user
can save after each NT refresh to track how recommendations evolve.

Public API:
    save_coupon_snapshot(...)        -> str           (snapshot_id)
    list_saved_snapshots(...)        -> list[dict]
    get_saved_snapshot(snapshot_id)  -> dict | None
    compare_saved_snapshots(...)     -> list[dict]
    delete_saved_snapshot(...)       -> bool
    evaluate_saved_snapshot(...)     -> dict
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from db.connection import get_conn


# ── Save ──────────────────────────────────────────────────────────────────────

def save_coupon_snapshot(
    coupon_id: str,
    strategy: str,
    budget: float,
    total_rows: int,
    cost_nok: float,
    p_win: float | None,
    pvr: float | None,
    singles_count: int,
    half_cover_count: int,
    full_cover_count: int,
    picks_data: list[dict],
    *,
    p_11_plus: float | None = None,
    p_10_plus: float | None = None,
    data_snapshot_time: str | None = None,
    model_version: str = "v5",
    optimizer_version: str = "v1",
) -> str:
    """
    Save an immutable snapshot of the current optimizer output.

    picks_data is a list of 12 dicts, each containing:
        fixture_id, match_number, home_team, away_team,
        pick, coverage_type, selected_outcomes (list),
        model_prob_h/u/b, pub_prob_h/u/b,
        confidence, crowd_disagreement_score,
        value_h/u/b, odds_source

    Returns the new snapshot_id.
    """
    with get_conn() as conn:
        # Resolve coupon metadata for denormalization
        meta = conn.execute(
            "SELECT week, year, day_type, label FROM coupons WHERE coupon_id=?",
            (coupon_id,),
        ).fetchone()
        week      = meta["week"]      if meta else None
        year      = meta["year"]      if meta else None
        day_type  = meta["day_type"]  if meta else None
        label     = meta["label"]     if meta else None

    # Compute aggregate metrics from picks
    cds_values = [
        p["crowd_disagreement_score"]
        for p in picks_data
        if p.get("crowd_disagreement_score") is not None
    ]
    avg_cds = sum(cds_values) / len(cds_values) if cds_values else None

    vi_values = []
    for p in picks_data:
        pick = p.get("pick") or p.get("recommendation")
        if not pick:
            continue
        mp_map = {
            "H": p.get("model_prob_h"),
            "U": p.get("model_prob_u"),
            "B": p.get("model_prob_b"),
        }
        pp_map = {
            "H": p.get("pub_prob_h"),
            "U": p.get("pub_prob_u"),
            "B": p.get("pub_prob_b"),
        }
        mp = mp_map.get(pick)
        pp = pp_map.get(pick)
        if mp and pp and pp > 0:
            vi_values.append(mp / pp)
    avg_vi = sum(vi_values) / len(vi_values) if vi_values else None

    pub_dev_values = []
    for p in picks_data:
        pick = p.get("pick") or p.get("recommendation")
        if not pick:
            continue
        val_map = {"H": p.get("value_h"), "U": p.get("value_u"), "B": p.get("value_b")}
        val = val_map.get(pick)
        if val is not None:
            pub_dev_values.append(abs(val))
    avg_public_deviation = (
        sum(pub_dev_values) / len(pub_dev_values) if pub_dev_values else None
    )

    snapshot_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_conn() as conn:
        conn.execute(
            """INSERT INTO saved_coupons
               (snapshot_id, coupon_id, strategy, budget_nok,
                total_rows, cost_nok,
                singles_count, half_cover_count, full_cover_count,
                p_win, pvr, p_11_plus, p_10_plus,
                avg_cds, avg_vi, avg_public_deviation,
                model_version, optimizer_version, data_snapshot_time,
                saved_at, week, year, day_type, coupon_label)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (snapshot_id, coupon_id, strategy, budget,
             total_rows, cost_nok,
             singles_count, half_cover_count, full_cover_count,
             p_win, pvr, p_11_plus, p_10_plus,
             avg_cds, avg_vi, avg_public_deviation,
             model_version, optimizer_version, data_snapshot_time,
             now, week, year, day_type, label),
        )

        for p in picks_data:
            pick = p.get("pick") or p.get("recommendation") or ""
            sel  = p.get("selected_outcomes", [pick]) if pick else []
            if isinstance(sel, str):
                sel = json.loads(sel)

            mp_pick = {
                "H": p.get("model_prob_h"),
                "U": p.get("model_prob_u"),
                "B": p.get("model_prob_b"),
            }.get(pick)
            pp_pick = {
                "H": p.get("pub_prob_h"),
                "U": p.get("pub_prob_u"),
                "B": p.get("pub_prob_b"),
            }.get(pick)
            vi = (mp_pick / pp_pick) if (mp_pick and pp_pick and pp_pick > 0) else None

            conn.execute(
                """INSERT INTO saved_coupon_picks
                   (pick_id, snapshot_id, fixture_id, match_number,
                    home_team, away_team, pick, coverage_type, selected_outcomes,
                    model_prob_h, model_prob_u, model_prob_b,
                    public_prob_h, public_prob_u, public_prob_b,
                    picked_prob, conviction, cds, vi,
                    value_h, value_u, value_b)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), snapshot_id,
                 p.get("fixture_id"), p.get("match_number"),
                 p.get("home_team", ""), p.get("away_team", ""),
                 pick, p.get("coverage_type", "single"),
                 json.dumps(sel),
                 p.get("model_prob_h"), p.get("model_prob_u"), p.get("model_prob_b"),
                 p.get("pub_prob_h"),   p.get("pub_prob_u"),   p.get("pub_prob_b"),
                 mp_pick, p.get("confidence"), p.get("crowd_disagreement_score"), vi,
                 p.get("value_h"), p.get("value_u"), p.get("value_b")),
            )

    return snapshot_id


# ── List ──────────────────────────────────────────────────────────────────────

def list_saved_snapshots(
    coupon_id: str | None = None,
    week: int | None = None,
    year: int | None = None,
) -> list[dict]:
    """
    List saved snapshots, newest first.
    Optionally filter by coupon_id or by week/year.
    """
    clauses: list[str] = []
    params: list = []
    if coupon_id:
        clauses.append("sc.coupon_id = ?")
        params.append(coupon_id)
    if week is not None:
        clauses.append("sc.week = ?")
        params.append(week)
    if year is not None:
        clauses.append("sc.year = ?")
        params.append(year)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with get_conn() as conn:
        rows = conn.execute(
            f"""SELECT
                    sc.snapshot_id, sc.coupon_id, sc.strategy, sc.budget_nok,
                    sc.total_rows, sc.cost_nok,
                    sc.singles_count, sc.half_cover_count, sc.full_cover_count,
                    sc.p_win, sc.pvr, sc.p_11_plus, sc.p_10_plus,
                    sc.avg_cds, sc.avg_vi, sc.avg_public_deviation,
                    sc.model_version, sc.optimizer_version, sc.data_snapshot_time,
                    sc.saved_at, sc.week, sc.year, sc.day_type, sc.coupon_label
                FROM saved_coupons sc
                {where}
                ORDER BY sc.saved_at DESC""",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ── Get one ───────────────────────────────────────────────────────────────────

def get_saved_snapshot(snapshot_id: str) -> dict | None:
    """Return full snapshot with all 12 picks. Includes evaluation if results available."""
    with get_conn() as conn:
        meta = conn.execute(
            """SELECT
                   sc.snapshot_id, sc.coupon_id, sc.strategy, sc.budget_nok,
                   sc.total_rows, sc.cost_nok,
                   sc.singles_count, sc.half_cover_count, sc.full_cover_count,
                   sc.p_win, sc.pvr, sc.p_11_plus, sc.p_10_plus,
                   sc.avg_cds, sc.avg_vi, sc.avg_public_deviation,
                   sc.model_version, sc.saved_at, sc.week, sc.year,
                   sc.day_type, sc.coupon_label
               FROM saved_coupons sc
               WHERE sc.snapshot_id = ?""",
            (snapshot_id,),
        ).fetchone()
        if not meta:
            return None

        picks = conn.execute(
            """SELECT
                   sp.pick_id, sp.snapshot_id, sp.fixture_id, sp.match_number,
                   sp.home_team, sp.away_team,
                   sp.pick, sp.coverage_type, sp.selected_outcomes,
                   sp.model_prob_h, sp.model_prob_u, sp.model_prob_b,
                   sp.public_prob_h, sp.public_prob_u, sp.public_prob_b,
                   sp.picked_prob, sp.conviction, sp.cds, sp.vi,
                   sp.value_h, sp.value_u, sp.value_b,
                   mr.result_1x2, mr.home_score, mr.away_score
               FROM saved_coupon_picks sp
               LEFT JOIN match_results mr ON mr.fixture_id = sp.fixture_id
               WHERE sp.snapshot_id = ?
               ORDER BY sp.match_number""",
            (snapshot_id,),
        ).fetchall()

    result = dict(meta)
    pick_list = []
    for p in picks:
        pd = dict(p)
        try:
            pd["selected_outcomes"] = json.loads(pd["selected_outcomes"])
        except Exception:
            pd["selected_outcomes"] = [pd["pick"]]
        result_1x2 = pd.get("result_1x2")
        pd["covered"] = (result_1x2 in pd["selected_outcomes"]) if result_1x2 else None
        pd["pick_correct"] = (result_1x2 == pd["pick"]) if result_1x2 else None
        pick_list.append(pd)

    result["picks"] = pick_list
    result["n_evaluated"] = sum(1 for p in pick_list if p.get("result_1x2"))

    # Compute evaluation summary if all 12 results available
    if result["n_evaluated"] == 12:
        result["correct_picks"]  = sum(1 for p in pick_list if p.get("covered"))
        result["all_covered"]    = int(result["correct_picks"] == 12)
        result["pick_accuracy"]  = sum(1 for p in pick_list if p.get("pick_correct"))
    else:
        result["correct_picks"]  = None
        result["all_covered"]    = None
        result["pick_accuracy"]  = None

    return result


# ── Compare ───────────────────────────────────────────────────────────────────

def compare_saved_snapshots(
    coupon_id: str | None = None,
    week: int | None = None,
    year: int | None = None,
) -> list[dict]:
    """
    Summary comparison of all saved snapshots for a coupon (or week/year).
    Returns compact dicts with the metrics needed for a comparison table.
    """
    return list_saved_snapshots(coupon_id=coupon_id, week=week, year=year)


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_saved_snapshot(snapshot_id: str) -> bool:
    """Delete a saved snapshot and its picks. Returns True if found and deleted."""
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT snapshot_id FROM saved_coupons WHERE snapshot_id=?",
            (snapshot_id,),
        ).fetchone()
        if not existing:
            return False
        conn.execute(
            "DELETE FROM saved_coupon_picks WHERE snapshot_id=?", (snapshot_id,)
        )
        conn.execute(
            "DELETE FROM saved_coupons WHERE snapshot_id=?", (snapshot_id,)
        )
    return True


# ── Evaluate ──────────────────────────────────────────────────────────────────

def evaluate_saved_snapshot(snapshot_id: str) -> dict:
    """
    Evaluate a saved snapshot against match_results.
    Idempotent — safe to call repeatedly as results come in.

    Returns {
        snapshot_id, evaluation_status,
        correct_picks, covered_picks, all_correct,
        n_total, n_evaluated,
        hit_10, hit_11, hit_12
    }
    """
    detail = get_saved_snapshot(snapshot_id)
    if not detail:
        return {"snapshot_id": snapshot_id, "evaluation_status": "not_found"}

    picks = detail.get("picks", [])
    n_total     = len(picks)
    has_result  = [p for p in picks if p.get("result_1x2")]
    n_evaluated = len(has_result)

    if n_evaluated == 0:
        return {
            "snapshot_id":       snapshot_id,
            "evaluation_status": "pending",
            "n_total":           n_total,
            "n_evaluated":       0,
            "correct_picks":     None,
            "covered_picks":     None,
            "all_correct":       0,
        }

    covered = sum(1 for p in has_result if p.get("covered"))
    pick_correct = sum(1 for p in has_result if p.get("pick_correct"))
    all_correct  = int(n_evaluated == n_total and covered == n_total)
    status       = "complete" if n_evaluated == n_total else "partial"

    return {
        "snapshot_id":       snapshot_id,
        "evaluation_status": status,
        "n_total":           n_total,
        "n_evaluated":       n_evaluated,
        "correct_picks":     covered,
        "covered_picks":     pick_correct,
        "all_correct":       all_correct,
        "hit_10":            int(covered >= 10),
        "hit_11":            int(covered >= 11),
        "hit_12":            int(covered == 12),
    }
