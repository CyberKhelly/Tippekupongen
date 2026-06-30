"""
Reset Modellspill ledger and generate fresh NT-only bets.

Steps:
  1. Count + hard-delete ALL model_bets (all statuses)
  2. Scrape NT Oddsen: 1X2 + BTTS + O/U 2.5 (Playwright headless)
  3. Generate candidates with nt_only=True:
       - no AF/Bet365 fallback for BTTS or O/U
       - no generic_prior
       - no odds < 1.50
       - no edge < 5pp
       - no placeholder odds (leg >= 8.00 or <= 1.10)
       - no contradictions
  4. Print full report + verify every new bet

Usage:
    python scripts/reset_and_rescan.py
"""
import sys
import json

sys.path.insert(0, ".")

W = 65

# ── Step 0: count existing bets ─────────────────────────────────────────────
from db.connection import get_conn
conn = get_conn()
counts = conn.execute(
    "SELECT status, COUNT(*) AS n FROM model_bets GROUP BY status"
).fetchall()
total_old = conn.execute("SELECT COUNT(*) FROM model_bets").fetchone()[0]
conn.close()

print(f"\n{'='*W}")
print("  MODELLSPILL RESET + FRESH NT SCAN")
print(f"{'='*W}")
print(f"\n  Existing bets before reset:")
for row in counts:
    print(f"    {row['status']:<12}: {row['n']}")
if not counts:
    print("    (none)")
print(f"    {'TOTAL':<12}: {total_old}")

# ── Step 1: delete all bets ──────────────────────────────────────────────────
from db.paper_bets import delete_all_model_bets
n_deleted = delete_all_model_bets()
print(f"\n  Deleted: {n_deleted} bets (all statuses)")

# ── Step 2: scrape NT Oddsen ─────────────────────────────────────────────────
print(f"\n  Scraping NT Oddsen (1X2 + BTTS + O/U 2.5)...")
from ingestion.nt_oddsen_playwright import scrape_nt_oddsen_playwright
scrape_result = scrape_nt_oddsen_playwright(verbose=False)

n_1x2   = scrape_result.get("n_stored",   0)
n_btts  = scrape_result.get("n_btts",     0)
n_ou25  = scrape_result.get("n_ou25",     0)
n_fix   = scrape_result.get("n_fixtures", 0)
scrape_err = scrape_result.get("error")

if scrape_err:
    print(f"  ERROR in NT scrape: {scrape_err}")
    sys.exit(1)

print(f"    NT fixtures scraped  : {n_fix}")
print(f"    1X2 rows stored      : {n_1x2}")
print(f"    BTTS rows stored     : {n_btts}")
print(f"    O/U 2.5 rows stored  : {n_ou25}")

# ── Step 3: generate NT-only candidates ─────────────────────────────────────
print(f"\n  Generating NT-only candidates (edge >= 5pp, no AF fallback)...")
from backend.main import generate_global_bet_candidates
result = generate_global_bet_candidates(nt_only=True)

n_new   = result["n_created"]
bm      = result.get("bets_by_market", {})
nm      = result.get("n_nt_matched", {})
ms      = result.get("market_stats", {})
rb      = result["rejection_breakdown"]
min_ep  = result["min_edge_pp"]
cands   = result.get("rejected_candidates", [])

print(f"\n{'='*W}")
print("  RESULTS")
print(f"{'='*W}")

print(f"\n  NT Oddsen fixture matches:")
print(f"    1X2 matched          : {nm.get('1x2', 0)}")
print(f"    BTTS matched         : {nm.get('btts', 0)}")
print(f"    O/U 2.5 matched      : {nm.get('over_2.5', 0)}")

print(f"\n  New bets generated: {n_new}")
print(f"    1X2                  : {bm.get('1x2', 0)}")
print(f"    BTTS                 : {bm.get('btts', 0)}")
print(f"    O/U 2.5              : {bm.get('over_2.5', 0)}")

if ms:
    print(f"\n  Edge statistics (NT-matched only, all evaluated):")
    print(f"    {'Market':<12}  {'n':>4}  {'max edge':>9}  {'avg edge':>9}  {'>= 5pp':>6}")
    print(f"    {'-'*12}  {'-'*4}  {'-'*9}  {'-'*9}  {'-'*6}")
    for mkt in ("1x2", "btts", "over_2.5"):
        if mkt not in ms:
            continue
        s = ms[mkt]
        print(
            f"    {mkt:<12}  {s['n_evaluated']:>4}  "
            f"{s['max_edge']:>+8.1f}pp  "
            f"{s['avg_edge']:>+8.1f}pp  "
            f"{s['n_above_threshold']:>4}/{s['n_evaluated']}"
        )

print(f"\n  Rejection breakdown (min edge {min_ep}pp, NT-only mode):")
for label, key in [
    (f"Edge < {min_ep}pp",        "edge_too_small"),
    ("Odds < 1.50",               "odds_too_low"),
    ("NT placeholder odds",       "nt_placeholder_odds"),
    ("No NT BTTS/O/U (NT-only)",  "no_nt_btts_ou"),
    ("No NT 1X2 odds",            "no_nt_odds_1x2"),
    ("No BTTS/O/U odds",          "no_btts_ou_odds"),
    ("Generic prior",             "generic_prior"),
    ("No enrichment (1X2)",       "no_enr_1x2"),
    ("AF 1X2 skipped",            "af_1x2_skipped"),
    ("Duplicate",                 "duplicate"),
    ("Contradictory",             "contradictory"),
    ("Bad/missing odds",          "bad_odds"),
    ("Error",                     "error"),
]:
    v = rb.get(key, 0)
    if v:
        print(f"    {label:<30}: {v}")

n_show = min(10, len(cands))
print(f"\n  Top {n_show} rejected candidates by EV (of {len(cands)} captured):")
if not cands:
    print("    (none)")
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
        odds_s = f"{c['ref_odds']:.2f}" if c.get("ref_odds") else "  N/A"
        ev_s   = f"{c['ev']:+.3f}"      if c.get("ev") is not None else "  N/A"
        qual   = c.get("model_quality", "")
        qual_s = f" [{qual[:4]}]" if qual else ""
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

# ── Step 4: verify new bets ──────────────────────────────────────────────────
print(f"\n{'='*W}")
print("  VERIFICATION OF NEW BETS")
print(f"{'='*W}")

conn2 = get_conn()
new_bets = conn2.execute(
    "SELECT * FROM model_bets ORDER BY created_at DESC"
).fetchall()
conn2.close()

issues = []
for b in new_bets:
    bid  = b["id"][:8]
    name = b["match_name"]

    if b["bookmaker"] != "NT Oddsen":
        issues.append(f"  [{bid}] {name}: bookmaker={b['bookmaker']!r} (expected NT Oddsen)")

    # True decimal EV = model_prob * ref_odds - 1
    expected_ev = round(b["model_prob"] * b["ref_odds"] - 1, 4)
    stored_ev   = round(b["expected_value"], 4) if b["expected_value"] is not None else None
    if stored_ev is None or abs(stored_ev - expected_ev) > 0.0005:
        issues.append(
            f"  [{bid}] {name}: EV={stored_ev} stored vs {expected_ev} expected"
        )

    if not b["debug_json"]:
        issues.append(f"  [{bid}] {name}: debug_json is NULL")
    else:
        try:
            dbg = json.loads(b["debug_json"])
            if b["market"] in ("btts", "over_2.5"):
                if not dbg.get("nt_odds"):
                    issues.append(f"  [{bid}] {name} {b['market']}: nt_odds missing from debug_json")
                if not dbg.get("nt_implied_prob"):
                    issues.append(f"  [{bid}] {name} {b['market']}: nt_implied_prob missing from debug_json")
                if dbg.get("odds_source") != "NT Oddsen":
                    issues.append(f"  [{bid}] {name} {b['market']}: odds_source={dbg.get('odds_source')!r}")
            elif b["market"] == "1x2":
                if not dbg.get("nt_odds_h"):
                    issues.append(f"  [{bid}] {name} 1x2: nt_odds_h missing from debug_json")
        except Exception as e:
            issues.append(f"  [{bid}] {name}: debug_json parse error: {e}")

if not new_bets:
    print(f"\n  No new bets generated — nothing to verify.")
elif not issues:
    print(f"\n  All {len(new_bets)} bets PASSED verification:")
    print(f"    bookmaker = NT Oddsen             : OK")
    print(f"    expected_value = model_prob*odds-1: OK")
    print(f"    debug_json populated              : OK")
    print(f"    nt_odds present in debug_json     : OK")
    print(f"    nt_implied_prob present           : OK")
    print(f"    odds_source = NT Oddsen           : OK")
else:
    print(f"\n  ISSUES FOUND ({len(issues)}):")
    for iss in issues:
        print(iss)

# Per-bet detail
if new_bets:
    print(f"\n  New bets detail:")
    hdr2 = (
        f"  {'Match':<28}  {'Mkt':<9}  {'Sel':<5}  "
        f"{'Odds':>5}  {'Edge':>7}  {'EV':>7}  {'Stake':>5}  Model%"
    )
    print(hdr2)
    print(f"  {'-'*28}  {'-'*9}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*7}  {'-'*5}  {'-'*6}")
    for b in new_bets:
        ev_s = f"{b['expected_value']:+.4f}" if b["expected_value"] is not None else "  N/A"
        print(
            f"  {b['match_name'][:28]:<28}  "
            f"{b['market']:<9}  "
            f"{b['outcome']:<5}  "
            f"{b['ref_odds']:>5.2f}  "
            f"{b['edge_pp']:>+6.1f}pp  "
            f"{ev_s:>7}  "
            f"{int(b['stake_nok']):>5}  "
            f"{b['model_prob']*100:.1f}%"
        )

print(f"\n{'='*W}\n")
