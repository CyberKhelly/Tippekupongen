"""
Automated coupon evaluation pipeline (Phase 8A).

Usage:
    python evaluate.py --week 24 --year 2026        # evaluate saved coupons for a week
    python evaluate.py --all                         # evaluate every coupon with predictions
    python evaluate.py --week 24 --year 2026 --fetch # also fetch results from API-Football
    python evaluate.py --status                      # show which coupons need evaluation

The pipeline is fully idempotent — re-running is safe and updates existing rows.

Result sources (in priority order):
  1. Manual results already in match_results (entered via Resultater page)
  2. API-Football results fetched when --fetch is given and kickoff + 2h <= now

Coupons with no results are marked 'pending' and skipped without error.
Coupons with partial results are marked 'partial' and evaluated on available data.
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone, timedelta

from db.schema import init_db
from db.connection import get_conn
from db.history import save_result
from db.evaluation import evaluate_coupon


# ── Result fetching from API-Football ────────────────────────────────────────

def _fetch_af_result(fixture_id: str, af_fixture_id: int) -> tuple[int, int] | None:
    """
    Fetch final score for one fixture from API-Football.
    Returns (home_score, away_score) if the match is finished, else None.
    """
    try:
        from ingestion.api_football import get_fixtures
        results = get_fixtures(fixture_id=af_fixture_id)
        if not results:
            return None
        fix = results[0]
        status = fix.get("fixture", {}).get("status", {}).get("short", "")
        # FT = full time, AET = after extra time, PEN = penalties
        if status not in ("FT", "AET", "PEN"):
            return None
        goals = fix.get("goals", {})
        home_g = goals.get("home")
        away_g = goals.get("away")
        if home_g is None or away_g is None:
            return None
        return int(home_g), int(away_g)
    except Exception as exc:
        print(f"  AF fetch error for fixture {fixture_id}: {exc}", file=sys.stderr)
        return None


def _is_kickoff_past(kickoff_utc: str, buffer_hours: int = 2) -> bool:
    """Returns True if kickoff + buffer has elapsed (match likely finished)."""
    try:
        ko = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        return datetime.now(timezone.utc) >= ko + timedelta(hours=buffer_hours)
    except Exception:
        return False


def fetch_results_for_coupons(coupon_ids: list[str]) -> dict[str, int]:
    """
    For each fixture in the given coupons, try to fetch result from API-Football
    if the match is finished and a result is not already saved.

    Returns {fixture_id: 1} for newly saved results.
    """
    saved: dict[str, int] = {}

    with get_conn() as conn:
        # Gather distinct fixtures across all coupons that have AF links
        placeholders = ",".join("?" * len(coupon_ids))
        rows = conn.execute(
            f"""SELECT DISTINCT cf.fixture_id, f.kickoff_utc,
                       lnk.api_football_fixture_id
                FROM coupon_fixtures cf
                JOIN fixtures f ON f.fixture_id = cf.fixture_id
                LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = cf.fixture_id
                LEFT JOIN match_results mr ON mr.fixture_id = cf.fixture_id
                WHERE cf.coupon_id IN ({placeholders})
                  AND mr.fixture_id IS NULL
                  AND lnk.api_football_fixture_id IS NOT NULL""",
            tuple(coupon_ids),
        ).fetchall()

    for row in rows:
        fid      = row["fixture_id"]
        ko       = row["kickoff_utc"] or ""
        af_id    = row["api_football_fixture_id"]

        if not _is_kickoff_past(ko):
            continue

        score = _fetch_af_result(fid, af_id)
        if score is None:
            continue

        save_result(fid, score[0], score[1], source="api_football")
        saved[fid] = 1
        print(f"  Fetched result for {fid}: {score[0]}–{score[1]}")

    return saved


# ── Evaluation runner ─────────────────────────────────────────────────────────

def _coupons_for_week(week: int, year: int) -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT p.coupon_id
               FROM coupon_predictions p
               JOIN coupons c ON c.coupon_id = p.coupon_id
               WHERE c.week = ? AND c.year = ?""",
            (week, year),
        ).fetchall()
    return [r["coupon_id"] for r in rows]


def _all_coupons_with_predictions() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT coupon_id FROM coupon_predictions"
        ).fetchall()
    return [r["coupon_id"] for r in rows]


def _all_coupon_ids_with_generations() -> list[str]:
    """Coupon ids that have Phase 9 generation records (pending or partial evaluation)."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT DISTINCT g.coupon_id
               FROM coupon_generations g
               LEFT JOIN generation_results r ON r.generation_id = g.generation_id
               WHERE r.generation_id IS NULL
                  OR r.evaluation_status IN ('pending', 'partial')"""
        ).fetchall()
    return [r["coupon_id"] for r in rows]


def run_evaluation(coupon_ids: list[str], fetch: bool = False) -> None:
    if not coupon_ids:
        print("No coupons found.")
        return

    if fetch:
        print(f"Fetching results from API-Football for {len(coupon_ids)} coupon(s)...")
        new_results = fetch_results_for_coupons(coupon_ids)
        print(f"  Fetched {len(new_results)} new result(s).")

    print(f"\nEvaluating {len(coupon_ids)} coupon(s)...")
    for cid in coupon_ids:
        result = evaluate_coupon(cid)
        status = result.get("evaluation_status", "?")
        n_res  = result.get("n_results", 0)
        n_tot  = result.get("n_total",   0)
        hr     = result.get("hit_rate")
        cr     = result.get("cover_rate")
        strat  = result.get("strategy", "—")

        hr_s = f"{hr*100:.1f}%" if hr is not None else "—"
        cr_s = f"{cr*100:.1f}%" if cr is not None else "—"

        print(
            f"  {cid:<36}  [{status:8}]  "
            f"{n_res:2}/{n_tot} results  "
            f"hit={hr_s:6}  cov={cr_s:6}  strategy={strat}"
        )


def show_status() -> None:
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT
                   c.coupon_id, c.week, c.year, c.day_type,
                   COUNT(DISTINCT p.fixture_id)  AS n_pred,
                   COUNT(DISTINCT r.fixture_id)  AS n_res,
                   e.evaluation_status,
                   e.hit_rate
               FROM coupons c
               JOIN coupon_predictions p   ON p.coupon_id = c.coupon_id
               LEFT JOIN match_results r   ON r.fixture_id = p.fixture_id
               LEFT JOIN coupon_evaluations e ON e.coupon_id = c.coupon_id
               GROUP BY c.coupon_id
               ORDER BY c.deadline_utc DESC""",
        ).fetchall()

    if not rows:
        print("No coupons with predictions found.")
        return

    print(f"\n{'Coupon':<38} {'Wk':>4} {'Yr':>5}  {'Preds':>5}  {'Res':>4}  {'Status':<10}  Hit")
    print("-" * 78)
    for r in rows:
        hr  = r["hit_rate"]
        hr_s = f"{hr*100:.1f}%" if hr is not None else "—"
        st  = r["evaluation_status"] or "not run"
        print(
            f"  {r['coupon_id']:<36}  {r['week']:>3}  {r['year']:>5}  "
            f"{r['n_pred']:>5}  {r['n_res']:>4}  {st:<10}  {hr_s}"
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="TippeQpongen — coupon evaluation pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--week",          type=int,        help="Week number to evaluate")
    group.add_argument("--all",           action="store_true", help="Evaluate all coupons")
    group.add_argument("--status",        action="store_true", help="Show evaluation status")
    group.add_argument("--freeze-active", action="store_true",
                       help="Freeze all active coupons (all 12 strategy×budget combos) immediately")
    group.add_argument("--sweep", action="store_true",
                       help="Sweep pending generation evaluations against match_results")
    group.add_argument("--calibrate", action="store_true",
                       help="Run calibration report (conviction/coverage/VI/CDS)")
    parser.add_argument("--year",      type=int, default=None, help="Year (required with --week)")
    parser.add_argument("--coupon-id", type=str, default=None,
                        help="With --freeze-active: force-freeze a specific coupon_id "
                             "(bypasses active-coupon filter — use for missed deadlines)")
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch missing results from API-Football before evaluating")

    args = parser.parse_args()

    init_db()

    if args.sweep:
        from db.generation import sweep_pending_evaluations
        print("Sweeping pending generation evaluations...")
        results = sweep_pending_evaluations()
        n_complete = sum(1 for r in results if r.get("evaluation_status") == "complete")
        n_partial  = sum(1 for r in results if r.get("evaluation_status") == "partial")
        n_pending  = sum(1 for r in results if r.get("evaluation_status") == "pending")
        print(f"  Swept {len(results)} generation(s): "
              f"{n_complete} complete, {n_partial} partial, {n_pending} still pending.")
        sys.exit(0)

    if args.calibrate:
        import importlib.util, pathlib
        _spec = importlib.util.spec_from_file_location(
            "calibration_report",
            pathlib.Path(__file__).parent / "scripts" / "calibration_report.py",
        )
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        run_calibration_report = _mod.run_calibration_report
        from db.generation import sweep_pending_evaluations
        swept = sweep_pending_evaluations()
        n_new = sum(1 for r in swept if r.get("evaluation_status") == "complete")
        if n_new:
            print(f"  Swept {n_new} newly completed evaluation(s).")
        run_calibration_report()
        sys.exit(0)

    if args.freeze_active:
        from backend.freeze import freeze_active_coupons, freeze_recently_expired

        if args.coupon_id:
            # Retroactively freeze a specific expired coupon by coupon_id.
            # Bypasses the active-coupon filter — use for missed deadlines.
            from collections import Counter
            from analysis.optimizer import optimize_coupon
            from analysis.pool_value import compute_p_win, compute_pool_value_ratio
            from backend.freeze import STRATEGIES, BUDGETS, _picks_data
            from backend.pipeline import build_matches
            from db.generation import freeze_coupon_combo
            from db.schema import init_db as _init
            _init()
            coupon_id = args.coupon_id
            print(f"Force-freezing {coupon_id} (all 12 strategy×budget combinations)…")
            try:
                matches = build_matches(coupon_id)
            except Exception as exc:
                print(f"ERROR: build_matches failed: {exc}", file=sys.stderr)
                sys.exit(1)
            results = []
            for strategy in STRATEGIES:
                for budget in BUDGETS:
                    try:
                        picks, total_rows = optimize_coupon(matches, budget, strategy=strategy)
                        p_win = compute_p_win(matches, picks)
                        pvr   = compute_pool_value_ratio(matches, picks)
                        n_s   = sum(1 for m in matches if len(picks[m.number]) == 1)
                        n_h   = sum(1 for m in matches if len(picks[m.number]) == 2)
                        n_f   = sum(1 for m in matches if len(picks[m.number]) == 3)
                        cov   = dict(Counter(len(m.stats_signals or []) for m in matches))
                        res   = freeze_coupon_combo(
                            coupon_id=coupon_id, strategy=strategy, budget=budget,
                            row_count=total_rows, p_win=p_win, pvr=pvr,
                            n_singles=n_s, n_halvdekk=n_h, n_heldekk=n_f,
                            coverage_dist=cov, picks_data=_picks_data(matches, picks),
                        )
                        if res:
                            results.append({"coupon_id": coupon_id, "strategy": strategy,
                                            "budget": budget, **res})
                    except Exception as exc:
                        results.append({"coupon_id": coupon_id, "strategy": strategy,
                                        "budget": budget, "error": str(exc)})
        else:
            print("Freezing all active coupons (all 12 strategy×budget combinations)…")
            results = freeze_active_coupons(force=True)

        n_created  = sum(1 for r in results if r.get("action") == "created")
        n_upgraded = sum(1 for r in results if r.get("action") == "upgraded")
        n_already  = sum(1 for r in results if r.get("action") == "already_frozen")
        n_errors   = sum(1 for r in results if r.get("error"))
        print(f"\nResult: {n_created + n_upgraded} frozen "
              f"({n_created} created, {n_upgraded} upgraded from live), "
              f"{n_already} already frozen, {n_errors} errors.")
        for r in results:
            if r.get("error"):
                s = r.get("strategy", "?")
                b = r.get("budget", "?")
                print(f"  ERROR  {r['coupon_id']}  {s}  {b} NOK: {r['error']}")
            elif r.get("action") in ("created", "upgraded"):
                print(f"  FROZEN {r['coupon_id']}  {r['strategy']}  {r['budget']} NOK  [{r['action']}]")
        sys.exit(0)

    if args.status:
        show_status()
        return

    if args.week is not None:
        year = args.year
        if year is None:
            year = datetime.now().year
        coupon_ids = _coupons_for_week(args.week, year)
        if not coupon_ids:
            print(f"No coupons with predictions found for week {args.week}/{year}.")
            sys.exit(0)
        run_evaluation(coupon_ids, fetch=args.fetch)
    else:
        coupon_ids = _all_coupons_with_predictions()

        # Phase 9 — when --fetch is given, also include generation coupon_ids so
        # fetch_results_for_coupons() can find the fixtures even when coupon_predictions
        # is empty (cleared at Phase 8A baseline reset).
        if args.fetch:
            gen_coupon_ids = _all_coupon_ids_with_generations()
            fetch_ids = list(set(coupon_ids) | set(gen_coupon_ids))
            if fetch_ids:
                print(f"Fetching results from API-Football for {len(fetch_ids)} coupon(s) "
                      f"({len(coupon_ids)} Phase 8A + {len(gen_coupon_ids)} Phase 9)...")
                new_results = fetch_results_for_coupons(fetch_ids)
                print(f"  Fetched {len(new_results)} new result(s).")
            else:
                print("No coupons to fetch results for.")
            # Run Phase 8A evaluation with original (possibly empty) list, no re-fetch
            run_evaluation(coupon_ids, fetch=False)
        else:
            run_evaluation(coupon_ids, fetch=False)

        # Phase 9 — sweep generation results
        try:
            from db.generation import sweep_pending_evaluations
            gen_results = sweep_pending_evaluations()
            n_complete = sum(1 for r in gen_results if r.get("evaluation_status") == "complete")
            n_partial  = sum(1 for r in gen_results if r.get("evaluation_status") == "partial")
            if gen_results:
                print(f"\nPhase 9 generations swept: {len(gen_results)} total, "
                      f"{n_complete} complete, {n_partial} partial.")
        except Exception as exc:
            print(f"Warning: generation sweep failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
