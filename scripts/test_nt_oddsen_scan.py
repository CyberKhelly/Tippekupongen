"""
Manual test: scrape NT Oddsen + run bet generation.

Usage:
    python scripts/test_nt_oddsen_scan.py

Requires FIRECRAWL_API_KEY in .env or environment.
Does NOT auto-create or modify production bets — just prints what would be generated.
Run with --commit to actually store the bets.
"""
import sys
import json

sys.path.insert(0, ".")

def _load_dotenv():
    from pathlib import Path
    try:
        for line in Path(".env").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                import os
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_dotenv()

commit = "--commit" in sys.argv

print("=" * 60)
print("  NT Oddsen Scan Test")
print("=" * 60)

# Step 1: scrape NT Oddsen
print("\n[1/3] Scraping NT Oddsen via Firecrawl...")
from ingestion.nt_oddsen_scraper import scrape_nt_oddsen
nt = scrape_nt_oddsen(wait_ms=5000, verbose=True)
if "error" in nt:
    print(f"\nScrape failed: {nt['error']} — {nt.get('message','')}")
    sys.exit(1)

print(f"\n  Matches extracted : {nt['n_matches']}")
print(f"  Rows stored       : {nt['n_rows_stored']}")
print(f"  Markets           : {nt['markets_found']}")

# Step 2: show what fixtures are in the NT snapshot
print("\n[2/3] NT Oddsen fixture keys in snapshot (last 6h):")
from db.connection import get_conn
conn = get_conn()
rows = conn.execute(
    """SELECT DISTINCT fixture_key, home_team, away_team, kickoff_iso, league
       FROM nt_oddsen_odds_snapshot
       WHERE scraped_at >= datetime('now', '-6 hours')
       ORDER BY kickoff_iso""",
).fetchall()
print(f"  {len(rows)} unique fixtures:")
for r in rows[:20]:
    print(f"    {r['fixture_key']:50}  kickoff={r['kickoff_iso'] or '?':16}  league={r['league'] or '?'}")
if len(rows) > 20:
    print(f"    ... and {len(rows)-20} more")
conn.close()

# Step 3: run candidate generation
print("\n[3/3] Running generate_global_bet_candidates(nt_odds_only=True)...")
if not commit:
    print("  (dry run — bets will NOT be stored; pass --commit to store)")

from backend.main import generate_global_bet_candidates
result = generate_global_bet_candidates(nt_odds_only=True)

print(f"\n  Evaluated   : {result['n_evaluated']}")
print(f"  Created     : {result['n_created']}")
print(f"  Min edge    : {result['min_edge_pp']}pp")
print(f"\n  Rejection breakdown:")
for k, v in result['rejection_breakdown'].items():
    print(f"    {k:25}: {v}")
print(f"\n  Tiers: A={result['tiers']['a']}  B={result['tiers']['b']}  C={result['tiers']['c']}")

if result['n_created'] > 0:
    print("\n  New bets created:")
    conn2 = get_conn()
    bets = conn2.execute(
        """SELECT match_name, market, outcome, ref_odds, edge_pp, model_quality, reason
           FROM model_bets
           WHERE status = 'pending'
           ORDER BY created_at DESC LIMIT 20""",
    ).fetchall()
    conn2.close()
    for b in bets:
        print(f"    {b['match_name']:35} {b['market']:8} {b['outcome']:6} "
              f"odds={b['ref_odds']:.2f}  edge={b['edge_pp']:+.1f}pp  [{b['model_quality']}]")
