"""
NT Oddsen Playwright scan test + bet generation report.

Usage:
    python scripts/test_nt_oddsen_scan.py
    python scripts/test_nt_oddsen_scan.py --commit   # actually store bets

Runs the full pipeline:
  1. Scrape NT Oddsen 1X2 odds via Playwright
  2. Show which fixtures are in the NT snapshot
  3. Run generate_global_bet_candidates() (dry run by default)
  4. Show full rejection breakdown with NT-specific counters

Does NOT commit bets unless --commit is passed.
"""
import sys

sys.path.insert(0, ".")
commit = "--commit" in sys.argv

print("=" * 62)
print("  NT Oddsen Scan Test  (Playwright)")
print("=" * 62)

# 1: Scrape NT Oddsen
print("\n[1/4] Scraping NT Oddsen via Playwright...")
from ingestion.nt_oddsen_playwright import scrape_nt_oddsen_playwright
nt = scrape_nt_oddsen_playwright(verbose=True)

if nt.get("error") and not nt.get("n_matches"):
    print(f"\n  ERROR: {nt['error']}")
    print("  Message:", nt.get("message", ""))
    sys.exit(1)

print(f"\n  NT matches extracted : {nt['n_matches']}")
print(f"  Rows stored          : {nt['n_rows_stored']}")
if nt.get("error"):
    print(f"  Warning              : {nt['error']}")

if nt["n_matches"] > 0:
    print("\n  Scraped matches:")
    for m in nt["matches"][:20]:
        print(
            f"    {m['home_team'][:20]:20} vs {m['away_team'][:20]:20}"
            f"  H={m['odds_h']:.2f}  U={m['odds_u']:.2f}  B={m['odds_b']:.2f}"
            f"  {m.get('kickoff_raw',''):18}  key={m['fixture_key']}"
        )
    if len(nt["matches"]) > 20:
        print(f"    ... and {len(nt['matches'])-20} more")

# 2: Show NT snapshot in DB
print("\n[2/4] NT Oddsen fixture keys in snapshot (last 6h):")
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
    print(f"    {r['fixture_key']:55}  kickoff={r['kickoff_iso'] or '?':16}  {r['league'] or ''}")
if len(rows) > 20:
    print(f"    ... and {len(rows)-20} more")
conn.close()

# 3: Show model fixtures (from odds table) to see potential matches
print("\n[3/4] Model fixtures in DB (upcoming, with 1X2 odds):")
from db.connection import get_conn
from ingestion.nt_oddsen_playwright import normalize_team_name, load_nt_odds_bulk
conn2 = get_conn()
nt_map = load_nt_odds_bulk(conn2)
model_rows = conn2.execute(
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
conn2.close()

n_matched = 0
n_unmatched = 0
print(f"  {len(model_rows)} upcoming fixtures:")
for r in model_rows:
    ko_date = (r["kickoff_utc"] or "")[:10]
    fk = f"{normalize_team_name(r['home_name'])}|{normalize_team_name(r['away_name'])}|{ko_date}"
    matched = fk in nt_map
    if matched:
        n_matched += 1
        nt_odds = nt_map[fk]
        print(
            f"    [OK] {r['home_name'][:18]:18} vs {r['away_name'][:18]:18}"
            f"  {ko_date}  NT: H={nt_odds['H']:.2f} U={nt_odds['U']:.2f} B={nt_odds['B']:.2f}"
        )
    else:
        n_unmatched += 1
        print(f"    [--] {r['home_name'][:18]:18} vs {r['away_name'][:18]:18}  {ko_date}  (no NT odds)")

print(f"\n  Matched: {n_matched}  Unmatched: {n_unmatched}")

# 4: Generate bet candidates
print(f"\n[4/4] Running generate_global_bet_candidates()...")
print("  (runs live -- bets are created in DB if edge >= 5pp)")

from backend.main import generate_global_bet_candidates
result = generate_global_bet_candidates()

print(f"\n  Evaluated       : {result['n_evaluated']}")
print(f"  Created         : {result['n_created']}")
print(f"  Min edge        : {result['min_edge_pp']}pp")
print(f"\n  Rejection breakdown:")
for k, v in result["rejection_breakdown"].items():
    tag = ""
    if k == "no_nt_odds_1x2" and v > 0:
        tag = "  <-- model fixtures without NT match"
    print(f"    {k:25}: {v}{tag}")
print(f"\n  Tiers: A={result['tiers']['a']}  B={result['tiers']['b']}  C={result['tiers']['c']}")

if result["n_created"] > 0:
    print("\n  New 1X2 bets (NT Oddsen):")
    conn3 = get_conn()
    bets = conn3.execute(
        """SELECT match_name, market, outcome, bookmaker, ref_odds, edge_pp, model_quality, reason
           FROM model_bets
           WHERE status = 'pending' AND market = '1x2'
           ORDER BY created_at DESC LIMIT 20""",
    ).fetchall()
    conn3.close()
    for b in bets:
        print(
            f"    {b['match_name'][:35]:35} {b['outcome']:4}"
            f"  odds={b['ref_odds']:.2f}  edge={b['edge_pp']:+.1f}pp"
            f"  [{b['model_quality']}]  via {b['bookmaker']}"
        )
