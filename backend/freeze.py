"""
Frozen snapshot management for generation-based historical tracking.

freeze_active_coupons() runs the full optimizer for all 12 (strategy × budget)
combinations and saves each as a frozen generation record. Called by:
  - APScheduler: automatically when a coupon is within FREEZE_WINDOW_MINUTES of deadline
  - POST /v1/history/freeze-active: manual / testing endpoint (force=True)
  - evaluate.py --freeze-active: CLI command (force=True)
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta

STRATEGIES = ["safe", "balanced", "jackpot"]
BUDGETS = [32.0, 96.0, 192.0, 384.0]
FREEZE_WINDOW_MINUTES = 60

_COVERAGE_TYPE = {1: "single", 2: "half_cover", 3: "full_cover"}


def _parse_deadline(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _picks_data(matches, picks) -> list[dict]:
    return [
        {
            "fixture_id":              m.fixture_id,
            "match_number":            m.number,
            "pick":                    m.recommendation or "",
            "coverage_type":           _COVERAGE_TYPE[len(picks[m.number])],
            "selected_outcomes":       picks[m.number],
            "confidence":              m.confidence,
            "model_prob_h":            m.prob_h,
            "model_prob_u":            m.prob_u,
            "model_prob_b":            m.prob_b,
            "pub_prob_h":              m.pub_prob_h,
            "pub_prob_u":              m.pub_prob_u,
            "pub_prob_b":              m.pub_prob_b,
            "value_h":                 m.value_h,
            "value_u":                 m.value_u,
            "value_b":                 m.value_b,
            "crowd_disagreement_score": m.crowd_disagreement_score,
            "odds_source":             m.odds_source,
            "has_af_data":             m.has_af_data,
        }
        for m in matches
    ]


def freeze_active_coupons(
    freeze_window_minutes: int = FREEZE_WINDOW_MINUTES,
    force: bool = False,
) -> list[dict]:
    """
    Freeze all active coupons that are within freeze_window_minutes of their deadline.

    force=True skips the deadline window check (used by manual endpoint and CLI).

    Returns a list of result dicts, one per (coupon, strategy, budget) combo:
      {"coupon_id", "strategy", "budget", "action": "created"|"upgraded"|"already_frozen"}
      or {"coupon_id", "strategy"?, "budget"?, "error": str}
    """
    from analysis.optimizer import optimize_coupon
    from analysis.pool_value import compute_p_win, compute_pool_value_ratio
    from backend.pipeline import build_matches
    from db.coupon import list_active_coupons
    from db.generation import freeze_coupon_combo

    active = list_active_coupons()
    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for coupon in active:
        deadline = _parse_deadline(coupon.get("deadline_utc"))
        if deadline is None:
            continue

        if not force and deadline > now + timedelta(minutes=freeze_window_minutes):
            continue  # too far from deadline, skip

        coupon_id = coupon["coupon_id"]

        try:
            matches = build_matches(coupon_id)
        except Exception as exc:
            results.append({"coupon_id": coupon_id, "error": str(exc)})
            continue

        for strategy in STRATEGIES:
            for budget in BUDGETS:
                try:
                    picks, total_rows = optimize_coupon(matches, budget, strategy=strategy)
                    p_win = compute_p_win(matches, picks)
                    pvr   = compute_pool_value_ratio(matches, picks)
                    n_singles  = sum(1 for m in matches if len(picks[m.number]) == 1)
                    n_halvdekk = sum(1 for m in matches if len(picks[m.number]) == 2)
                    n_heldekk  = sum(1 for m in matches if len(picks[m.number]) == 3)
                    cov_dist   = dict(Counter(len(m.stats_signals or []) for m in matches))

                    res = freeze_coupon_combo(
                        coupon_id=coupon_id,
                        strategy=strategy,
                        budget=budget,
                        row_count=total_rows,
                        p_win=p_win,
                        pvr=pvr,
                        n_singles=n_singles,
                        n_halvdekk=n_halvdekk,
                        n_heldekk=n_heldekk,
                        coverage_dist=cov_dist,
                        picks_data=_picks_data(matches, picks),
                    )
                    if res:
                        results.append({
                            "coupon_id": coupon_id,
                            "strategy":  strategy,
                            "budget":    budget,
                            **res,
                        })
                except Exception as exc:
                    results.append({
                        "coupon_id": coupon_id,
                        "strategy":  strategy,
                        "budget":    budget,
                        "error":     str(exc),
                    })

    return results


def freeze_recently_expired(lookback_hours: int = 24) -> list[dict]:
    """
    Catch-up freeze for coupons that expired in the last `lookback_hours` but
    have no frozen generations. Called at scheduler startup to recover from any
    freeze window missed while the backend was down.

    Returns the same result list as freeze_active_coupons().
    """
    from datetime import datetime, timezone, timedelta
    from db.connection import get_conn

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT c.coupon_id, c.deadline_utc
               FROM coupons c
               WHERE c.deadline_utc IS NOT NULL
                 AND NOT EXISTS (
                     SELECT 1 FROM coupon_generations g
                     WHERE g.coupon_id = c.coupon_id
                       AND g.status IN ('frozen', 'evaluated')
                 )"""
        ).fetchall()

    candidates: list[str] = []
    for row in rows:
        deadline = _parse_deadline(row["deadline_utc"])
        if deadline and cutoff <= deadline <= now:
            candidates.append(row["coupon_id"])

    if not candidates:
        return []

    from analysis.optimizer import optimize_coupon
    from analysis.pool_value import compute_p_win, compute_pool_value_ratio
    from backend.pipeline import build_matches
    from collections import Counter
    from db.generation import freeze_coupon_combo

    results: list[dict] = []
    for coupon_id in candidates:
        try:
            matches = build_matches(coupon_id)
        except Exception as exc:
            results.append({"coupon_id": coupon_id, "error": f"build_matches: {exc}"})
            continue

        for strategy in STRATEGIES:
            for budget in BUDGETS:
                try:
                    picks, total_rows = optimize_coupon(matches, budget, strategy=strategy)
                    p_win = compute_p_win(matches, picks)
                    pvr = compute_pool_value_ratio(matches, picks)
                    n_singles  = sum(1 for m in matches if len(picks[m.number]) == 1)
                    n_halvdekk = sum(1 for m in matches if len(picks[m.number]) == 2)
                    n_heldekk  = sum(1 for m in matches if len(picks[m.number]) == 3)
                    cov_dist   = dict(Counter(len(m.stats_signals or []) for m in matches))

                    res = freeze_coupon_combo(
                        coupon_id=coupon_id,
                        strategy=strategy,
                        budget=budget,
                        row_count=total_rows,
                        p_win=p_win,
                        pvr=pvr,
                        n_singles=n_singles,
                        n_halvdekk=n_halvdekk,
                        n_heldekk=n_heldekk,
                        coverage_dist=cov_dist,
                        picks_data=_picks_data(matches, picks),
                    )
                    if res:
                        results.append({
                            "coupon_id": coupon_id,
                            "strategy":  strategy,
                            "budget":    budget,
                            **res,
                        })
                except Exception as exc:
                    results.append({
                        "coupon_id": coupon_id,
                        "strategy":  strategy,
                        "budget":    budget,
                        "error":     str(exc),
                    })

    return results
