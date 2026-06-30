"""
Modellspill scan diagnostics — top N rejected candidates + per-market edge stats.

Does NOT re-scrape NT Oddsen.  Uses whatever is already in the snapshot.
Runs candidate evaluation and reports which bets nearly cleared the threshold.

Usage:
    python scripts/scan_diagnostics.py          # top 10 rejected
    python scripts/scan_diagnostics.py --n 20   # top 20
    python scripts/scan_diagnostics.py --all    # all captured (up to 50)
"""
import sys
sys.path.insert(0, ".")

N = 10
for i, a in enumerate(sys.argv[1:]):
    if a == "--all":
        N = 50
    elif a == "--n" and i + 1 < len(sys.argv[1:]):
        try:
            N = int(sys.argv[i + 2])
        except (ValueError, IndexError):
            pass

print("Running candidate evaluation (uses existing NT snapshot, no re-scrape)...")
from backend.main import generate_global_bet_candidates
result = generate_global_bet_candidates()

W = 65

print(f"\n{'='*W}")
print(f"  SCAN DIAGNOSTICS  ({result['n_evaluated']} fixtures evaluated)")
print(f"{'='*W}")

# Bets created
bm = result.get("bets_by_market", {})
nc = result.get("n_created", 0)
print(f"\n  Bets created             : {nc}")
print(f"    1X2                    : {bm.get('1x2', 0)}")
print(f"    BTTS                   : {bm.get('btts', 0)}")
print(f"    O/U 2.5                : {bm.get('over_2.5', 0)}")

# NT Oddsen match counts
nm = result.get("n_nt_matched", {})
print(f"\n  NT Oddsen matched:")
print(f"    1X2 (model + NT)       : {nm.get('1x2', 0)}")
print(f"    BTTS (NT primary)      : {nm.get('btts', 0)}")
print(f"    O/U 2.5 (NT primary)   : {nm.get('over_2.5', 0)}")

# Per-market edge statistics
ms = result.get("market_stats", {})
if ms:
    print(f"\n  Edge statistics (all evaluated candidates):")
    print(f"    {'Market':<12}  {'n':>4}  {'max edge':>9}  {'avg edge':>9}  {'>= threshold':>13}")
    print(f"    {'-'*12}  {'-'*4}  {'-'*9}  {'-'*9}  {'-'*13}")
    for mkt in ("1x2", "btts", "over_2.5"):
        if mkt not in ms:
            continue
        s = ms[mkt]
        print(
            f"    {mkt:<12}  {s['n_evaluated']:>4}  "
            f"{s['max_edge']:>+8.1f}pp  "
            f"{s['avg_edge']:>+8.1f}pp  "
            f"{s['n_above_threshold']:>8} / {s['n_evaluated']}"
        )

# Rejection breakdown
rb = result["rejection_breakdown"]
min_ep = result["min_edge_pp"]
print(f"\n  Rejection breakdown (min edge {min_ep}pp, min odds 1.50):")
for label, key in [
    (f"Edge < {min_ep}pp",     "edge_too_small"),
    ("Odds < 1.50",            "odds_too_low"),
    ("No NT 1X2 odds",         "no_nt_odds_1x2"),
    ("No BTTS/O/U odds",       "no_btts_ou_odds"),
    ("Generic prior",          "generic_prior"),
    ("No enrichment (1X2)",    "no_enr_1x2"),
    ("AF 1X2 skipped",         "af_1x2_skipped"),
    ("Duplicate",              "duplicate"),
    ("Contradictory",          "contradictory"),
    ("Bad/missing odds",       "bad_odds"),
    ("Error",                  "error"),
]:
    v = rb.get(key, 0)
    if v:
        print(f"    {label:<26}: {v}")

# Top N rejected candidates
cands = result.get("rejected_candidates", [])
n_show = min(N, len(cands))
print(f"\n  Top {n_show} rejected candidates by EV (of {len(cands)} total):")
if not cands:
    print("    (none — no evaluated candidates with odds available)")
else:
    hdr = (
        f"  {'Fixture':<28}  {'Market':<9}  {'Sel':<5}  "
        f"{'Odds':>5}  {'Model%':>7}  {'Impl%':>7}  "
        f"{'Edge':>7}  {'EV':>7}  Reason"
    )
    sep = (
        f"  {'-'*28}  {'-'*9}  {'-'*5}  "
        f"{'-'*5}  {'-'*7}  {'-'*7}  "
        f"{'-'*7}  {'-'*7}  {'-'*15}"
    )
    print(f"\n{hdr}")
    print(sep)
    for c in cands[:n_show]:
        odds_s  = f"{c['ref_odds']:.2f}"    if c.get("ref_odds") else "  N/A"
        ev_s    = f"{c['ev']:+.3f}"          if c.get("ev") is not None else "  N/A"
        qual    = c.get("model_quality", "")
        qual_s  = f" [{qual[:4]}]" if qual else ""
        print(
            f"  {c['fixture'][:28]:<28}  "
            f"{c['market']:<9}  "
            f"{c['selection']:<5}  "
            f"{odds_s:>5}  "
            f"{c['model_prob']*100:>6.1f}%  "
            f"{c['implied_prob']*100:>6.1f}%  "
            f"{c['edge_pp']:>+6.1f}pp  "
            f"{ev_s:>7}  "
            f"{c.get('reason','?')}{qual_s}"
        )

print(f"\n{'='*W}")
print("  Tip: run with --n 20 for more candidates, or --all for all 50 captured.")
print(f"{'='*W}\n")
