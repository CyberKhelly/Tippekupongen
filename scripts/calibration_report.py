"""
Calibration report for TippeIQ coupon engine.

Reads from generation_picks (frozen/evaluated) joined to match_results.
Requires at least one fully evaluated coupon.

Usage:
    python scripts/calibration_report.py
    python evaluate.py --calibrate
"""
from __future__ import annotations

import sys
sys.path.insert(0, ".")

from collections import defaultdict
from db.generation import get_calibration_picks, sweep_pending_evaluations


def _pct(n: int, d: int) -> str:
    return f"{n/d*100:5.1f}%" if d else "    —"


def _bucket_report(
    title: str,
    picks: list[dict],
    key_fn,
    buckets: dict[str, tuple[float, float]],
) -> None:
    """Print a pick_hit + coverage_hit table bucketed by key_fn(pick)."""
    data: dict[str, dict] = {
        label: {"pick": 0, "cov": 0, "total": 0} for label in buckets
    }
    for p in picks:
        v = key_fn(p)
        if v is None:
            continue
        for label, (lo, hi) in buckets.items():
            if lo <= v < hi:
                data[label]["total"] += 1
                data[label]["pick"] += p["pick_hit"]
                data[label]["cov"]  += p["coverage_hit"]
                break

    print(f"\n  {title}")
    print(f"  {'Bucket':<20}  {'n':>4}  {'Pick%':>6}  {'Coverage%':>9}")
    print(f"  {'-'*20}  {'-'*4}  {'-'*6}  {'-'*9}")
    for label in sorted(buckets.keys()):
        d = data[label]
        t = d["total"]
        print(
            f"  {label:<20}  {t:>4}  "
            f"{_pct(d['pick'], t):>6}  "
            f"{_pct(d['cov'],  t):>9}"
        )


def run_calibration_report(picks: list[dict] | None = None) -> None:
    if picks is None:
        picks = get_calibration_picks()

    W = 60

    if not picks:
        print("\nNo evaluated picks found.")
        print("Run: python evaluate.py --sweep   (then retry)\n")
        return

    n_total = len(picks)
    n_hits  = sum(p["pick_hit"]     for p in picks)
    n_cov   = sum(p["coverage_hit"] for p in picks)
    n_fxs   = len({p["fixture_id"]  for p in picks})

    # Public baseline
    pub_hits = pub_total = 0
    for p in picks:
        pp = {
            "H": p.get("pub_prob_h") or 0,
            "U": p.get("pub_prob_u") or 0,
            "B": p.get("pub_prob_b") or 0,
        }
        if any(pp.values()):
            pub_total += 1
            if max(pp, key=pp.get) == p["result_1x2"]:
                pub_hits += 1

    print(f"\n{'='*W}")
    print("  COUPON ENGINE CALIBRATION REPORT")
    print(f"{'='*W}")
    print(f"\n  {n_total} evaluated picks  ({n_fxs} distinct fixtures)")
    print(f"  Model pick accuracy : {n_hits}/{n_total} = {_pct(n_hits, n_total)}")
    print(f"  Coupon coverage rate: {n_cov}/{n_total} = {_pct(n_cov, n_total)}")
    print(f"  NT public accuracy  : {pub_hits}/{pub_total} = {_pct(pub_hits, pub_total)}")

    # Outcome distribution
    dist = defaultdict(int)
    for p in picks:
        dist[p["result_1x2"]] += 1
    print(
        f"\n  Outcome split: "
        f"H={dist['H']} ({_pct(dist['H'], n_total)})  "
        f"U={dist['U']} ({_pct(dist['U'], n_total)})  "
        f"B={dist['B']} ({_pct(dist['B'], n_total)})"
    )

    # ── Conviction calibration ────────────────────────────────────────────────
    _bucket_report(
        "CONVICTION  (confidence = model_prob of recommended pick)",
        picks,
        lambda p: p.get("confidence"),
        {
            "40-50%": (0.40, 0.50),
            "50-60%": (0.50, 0.60),
            "60-70%": (0.60, 0.70),
            "70-80%": (0.70, 0.80),
            "80%+":   (0.80, 1.01),
        },
    )

    # ── Coverage type calibration ─────────────────────────────────────────────
    print(f"\n  COVERAGE TYPE")
    cov_data: dict[str, dict] = defaultdict(lambda: {"pick": 0, "cov": 0, "total": 0})
    for p in picks:
        ct = p.get("coverage_type", "unknown")
        cov_data[ct]["total"] += 1
        cov_data[ct]["pick"]  += p["pick_hit"]
        cov_data[ct]["cov"]   += p["coverage_hit"]

    print(f"  {'Type':<14}  {'n':>4}  {'Pick%':>6}  {'Coverage%':>9}")
    print(f"  {'-'*14}  {'-'*4}  {'-'*6}  {'-'*9}")
    for ct in ["single", "half_cover", "full_cover"]:
        d = cov_data.get(ct)
        if d and d["total"]:
            t = d["total"]
            print(
                f"  {ct:<14}  {t:>4}  "
                f"{_pct(d['pick'], t):>6}  "
                f"{_pct(d['cov'],  t):>9}"
            )

    # ── Value Index (VI) calibration ──────────────────────────────────────────
    _bucket_report(
        "VALUE INDEX  (model_prob_pick / pub_prob_pick)",
        picks,
        lambda p: p.get("vi"),
        {
            "VI < 0.90":  (0.00, 0.90),
            "VI 0.90-1.0": (0.90, 1.00),
            "VI 1.0-1.1":  (1.00, 1.10),
            "VI 1.1-1.2":  (1.10, 1.20),
            "VI > 1.20":   (1.20, 99.0),
        },
    )

    # ── CDS calibration ───────────────────────────────────────────────────────
    _bucket_report(
        "CDS  (crowd disagreement score, pp)",
        picks,
        lambda p: p.get("crowd_disagreement_score"),
        {
            "0-5 pp":   (0.0,  5.0),
            "5-10 pp":  (5.0, 10.0),
            "10-20 pp": (10.0, 20.0),
            "> 20 pp":  (20.0, 100.0),
        },
    )

    # ── Strategy breakdown ────────────────────────────────────────────────────
    print(f"\n  STRATEGY BREAKDOWN")
    strat: dict[str, dict] = defaultdict(lambda: {"pick": 0, "cov": 0, "total": 0})
    for p in picks:
        s = p.get("strategy", "?")
        strat[s]["total"] += 1
        strat[s]["pick"]  += p["pick_hit"]
        strat[s]["cov"]   += p["coverage_hit"]

    print(f"  {'Strategy':<12}  {'n':>4}  {'Pick%':>6}  {'Coverage%':>9}")
    print(f"  {'-'*12}  {'-'*4}  {'-'*6}  {'-'*9}")
    for s in ["safe", "balanced", "jackpot"]:
        d = strat.get(s)
        if d and d["total"]:
            t = d["total"]
            print(
                f"  {s:<12}  {t:>4}  "
                f"{_pct(d['pick'], t):>6}  "
                f"{_pct(d['cov'],  t):>9}"
            )

    print(f"\n{'='*W}")
    n_per_fix = n_total // max(n_fxs, 1)
    print(f"  Sample size: {n_fxs} fixtures x {n_per_fix} generations each (n={n_total} rows).")
    print(f"  WARNING: rows are NOT independent -- same fixtures repeated across strategies.")
    print(f"  Interpret direction of trends only. Do not trust absolute percentages.")
    print(f"{'='*W}\n")


if __name__ == "__main__":
    # Sweep pending evaluations first so the report reflects latest data
    swept = sweep_pending_evaluations()
    n_new_complete = sum(1 for r in swept if r.get("evaluation_status") == "complete")
    if n_new_complete:
        print(f"  Swept {n_new_complete} newly completed evaluation(s).")
    run_calibration_report()
