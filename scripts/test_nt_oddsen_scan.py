"""
NT Oddsen full pipeline scan test.

Runs:
  1. Scrape NT Oddsen (1X2 + BTTS + O/U 2.5) via Playwright
  2. Show snapshot contents (fixtures + market coverage)
  3. Run generate_global_bet_candidates()
  4. Print full report

Usage:
    python scripts/test_nt_oddsen_scan.py
    python scripts/test_nt_oddsen_scan.py --commit   # actually store bets
"""
import sys

sys.path.insert(0, ".")

SEP = "=" * 62

# ── 1: Scrape NT Oddsen ───────────────────────────────────────────────
print(SEP)
print("  NT Oddsen Full Pipeline Scan Test")
print(SEP)
print("\n[1/4] Scraping NT Oddsen via Playwright (1X2 + BTTS + O/U)...")
from ingestion.nt_oddsen_playwright import scrape_nt_oddsen_playwright

nt = scrape_nt_oddsen_playwright(verbose=True)

if nt.get("error") and not nt.get("n_matches"):
    print(f"\n  ERROR: {nt['error']}")
    print("  Message:", nt.get("message", ""))
    sys.exit(1)

print(f"\n  NT fixtures scraped   : {nt['n_matches']}")
print(f"  BTTS odds found       : {nt.get('n_btts', 0)}/{nt['n_matches']}")
print(f"  O/U 2.5 odds found    : {nt.get('n_ou25', 0)}/{nt['n_matches']}")
print(f"  Rows stored           : {nt['n_rows_stored']}")
if nt.get("error"):
    print(f"  Warning               : {nt['error']}")

if nt["n_matches"] > 0:
    print("\n  Scraped matches (1X2):")
    for m in nt["matches"][:20]:
        print(
            f"    {m['home_team'][:20]:20} vs {m['away_team'][:20]:20}"
            f"  H={m['odds_h']:.2f}  U={m['odds_u']:.2f}  B={m['odds_b']:.2f}"
            f"  key={m['fixture_key']}"
        )
    if len(nt["matches"]) > 20:
        print(f"    ... and {len(nt['matches']) - 20} more")

# ── 2: Show snapshot market coverage ─────────────────────────────────
print("\n[2/4] NT Oddsen snapshot (last 6h) — market coverage:")
from db.connection import get_conn

conn = get_conn()

snapshot_rows = conn.execute(
    """SELECT fixture_key, home_team, away_team, market, COUNT(*) AS n
       FROM nt_oddsen_odds_snapshot
       WHERE scraped_at >= datetime('now', '-6 hours')
       GROUP BY fixture_key, market
       ORDER BY fixture_key, market"""
).fetchall()

from collections import defaultdict
coverage: dict[str, dict] = defaultdict(dict)
for r in snapshot_rows:
    coverage[r["fixture_key"]][r["market"]] = r["n"]

fixtures_1x2  = sum(1 for v in coverage.values() if "1x2" in v)
fixtures_btts = sum(1 for v in coverage.values() if "BTTS" in v)
fixtures_ou   = sum(1 for v in coverage.values() if "OVER_UNDER_2_5" in v)

print(f"\n  Unique fixtures in snapshot : {len(coverage)}")
print(f"  With 1X2 odds               : {fixtures_1x2}")
print(f"  With BTTS odds              : {fixtures_btts}")
print(f"  With O/U 2.5 odds           : {fixtures_ou}")

print(f"\n  Per-fixture market coverage:")
for fk, mkts in list(coverage.items())[:20]:
    has_1x2  = "Y" if "1x2" in mkts else "-"
    has_btts = "Y" if "BTTS" in mkts else "-"
    has_ou   = "Y" if "OVER_UNDER_2_5" in mkts else "-"
    print(f"    {fk[:55]:55}  1X2={has_1x2}  BTTS={has_btts}  O/U={has_ou}")
if len(coverage) > 20:
    print(f"    ... and {len(coverage) - 20} more")

# ── 3: Model fixture matching ─────────────────────────────────────────
print("\n[3/4] Model fixtures (upcoming, with 1X2 odds) vs NT snapshot:")
from ingestion.nt_oddsen_playwright import normalize_team_name, load_nt_odds_bulk, load_nt_market_bulk

nt_1x2_map  = load_nt_odds_bulk(conn)
nt_btts_map = load_nt_market_bulk(conn, "BTTS",           {"YES", "NO"})
nt_ou_map   = load_nt_market_bulk(conn, "OVER_UNDER_2_5", {"OVER", "UNDER"})

model_rows = conn.execute(
    """SELECT DISTINCT o.fixture_id,
              COALESCE(ht.name_local, ht2.name_local, f.home_name) AS home_name,
              COALESCE(at.name_local, at2.name_local, f.away_name) AS away_name,
              f.kickoff_utc
       FROM odds o
       JOIN fixtures f ON f.fixture_id = o.fixture_id
       LEFT JOIN teams ht  ON ht.team_id = f.home_team_id
       LEFT JOIN teams at  ON at.team_id = f.away_team_id
       LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = o.fixture_id
       LEFT JOIN teams ht2 ON ht2.external_id = lnk.api_football_home_team_id
       LEFT JOIN teams at2 ON at2.external_id = lnk.api_football_away_team_id
       WHERE f.kickoff_utc > datetime('now')
       ORDER BY f.kickoff_utc LIMIT 30""",
).fetchall()
conn.close()

n_matched_1x2 = n_matched_btts = n_matched_ou = 0
print(f"\n  {len(model_rows)} upcoming model fixtures:")
for r in model_rows:
    ko_date = (r["kickoff_utc"] or "")[:10]
    fk = f"{normalize_team_name(r['home_name'])}|{normalize_team_name(r['away_name'])}|{ko_date}"
    has_1x2  = fk in nt_1x2_map;  n_matched_1x2  += has_1x2
    has_btts = fk in nt_btts_map; n_matched_btts += has_btts
    has_ou   = fk in nt_ou_map;   n_matched_ou   += has_ou
    tag = f"{'1X2' if has_1x2 else '---'} {'BTTS' if has_btts else '----'} {'O/U' if has_ou else '---'}"
    print(f"    [{tag}]  {r['home_name'][:18]:18} vs {r['away_name'][:18]:18}  {ko_date}")

print(f"\n  NT match rate -- 1X2: {n_matched_1x2}/{len(model_rows)}  "
      f"BTTS: {n_matched_btts}/{len(model_rows)}  "
      f"O/U: {n_matched_ou}/{len(model_rows)}")

# ── 4: Generate bet candidates ────────────────────────────────────────
print(f"\n[4/4] Running generate_global_bet_candidates()...")
from backend.main import generate_global_bet_candidates

result = generate_global_bet_candidates()

bm = result.get("bets_by_market", {})
rb = result["rejection_breakdown"]

print(f"\n{'-'*50}")
print(f"  SCAN RESULTS")
print(f"{'-'*50}")
print(f"  Fixtures evaluated       : {result['n_evaluated']}")
print(f"  Total bets created       : {result['n_created']}")
print(f"  Min edge                 : {result['min_edge_pp']}pp")
print(f"\n  Bets by market:")
print(f"    1X2                    : {bm.get('1x2', 0)}")
print(f"    BTTS                   : {bm.get('btts', 0)}")
print(f"    O/U 2.5                : {bm.get('over_2.5', 0)}")
print(f"\n  Rejection breakdown:")
print(f"    No NT 1X2 odds         : {rb.get('no_nt_odds_1x2', 0)}")
print(f"    No BTTS/O/U odds       : {rb.get('no_btts_ou_odds', 0)}")
print(f"    Edge < {result['min_edge_pp']}pp           : {rb.get('edge_too_small', 0)}")
print(f"    Duplicate              : {rb.get('duplicate', 0)}")
print(f"    Generic prior          : {rb.get('generic_prior', 0)}")
print(f"    No enrichment (1X2)    : {rb.get('no_enr_1x2', 0)}")
print(f"    AF 1X2 skipped         : {rb.get('af_1x2_skipped', 0)}")
print(f"    Odds too low           : {rb.get('odds_too_low', 0)}")
print(f"    Contradictory          : {rb.get('contradictory', 0)}")
print(f"    Error                  : {rb.get('error', 0)}")
print(f"  Tiers: A={result['tiers']['a']}  B={result['tiers']['b']}  C={result['tiers']['c']}")

if result["n_created"] > 0:
    conn2 = get_conn()
    bets = conn2.execute(
        """SELECT match_name, market, outcome, bookmaker, ref_odds, edge_pp, model_quality, reason
           FROM model_bets
           WHERE status = 'pending'
           ORDER BY created_at DESC LIMIT 30""",
    ).fetchall()
    conn2.close()

    if bets:
        print(f"\n  Pending bets (all markets):")
        for b in bets:
            print(
                f"    {b['match_name'][:32]:32}  {b['market']:10}  {b['outcome']:5}"
                f"  odds={b['ref_odds']:.2f}  edge={b['edge_pp']:+.1f}pp"
                f"  [{b['model_quality']}]  via {b['bookmaker']}"
            )

print(f"\n{SEP}")
