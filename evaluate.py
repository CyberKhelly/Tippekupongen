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
    group.add_argument("--week",   type=int, help="Week number to evaluate")
    group.add_argument("--all",    action="store_true", help="Evaluate all coupons")
    group.add_argument("--status", action="store_true", help="Show evaluation status")
    parser.add_argument("--year",  type=int, default=None, help="Year (required with --week)")
    parser.add_argument("--fetch", action="store_true",
                        help="Fetch missing results from API-Football before evaluating")

    args = parser.parse_args()

    init_db()

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
        run_evaluation(coupon_ids, fetch=args.fetch)


if __name__ == "__main__":
    main()
