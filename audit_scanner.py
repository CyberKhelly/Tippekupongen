import sys
sys.path.insert(0, '.')
from db.connection import get_conn
from datetime import datetime, timezone, timedelta

conn = get_conn()
now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
window = (datetime.now(timezone.utc) + timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%SZ')

print("=== MODELLSPILL SCANNER AUDIT ===")
n_fix = conn.execute('SELECT COUNT(*) FROM fixtures WHERE kickoff_utc > ? AND kickoff_utc < ?', (now, window)).fetchone()[0]
print(f"Fixtures in DB (48h window): {n_fix}")

n_1x2 = conn.execute('''SELECT COUNT(DISTINCT o.fixture_id) FROM odds o
    JOIN fixtures f ON f.fixture_id=o.fixture_id
    WHERE f.kickoff_utc > ? AND f.kickoff_utc < ?''', (now, window)).fetchone()[0]
print(f"Fixtures with 1X2 odds:      {n_1x2}")

n_enr = conn.execute('''SELECT COUNT(DISTINCT fse.fixture_id) FROM fixture_stat_enrichment fse
    JOIN fixtures f ON f.fixture_id=fse.fixture_id
    WHERE f.kickoff_utc > ? AND f.kickoff_utc < ? AND fse.has_api_football_data=1''', (now, window)).fetchone()[0]
print(f"Fixtures with enrichment:    {n_enr}")

n_both = conn.execute('''SELECT COUNT(DISTINCT o.fixture_id) FROM odds o
    JOIN fixtures f ON f.fixture_id=o.fixture_id
    JOIN fixture_stat_enrichment fse ON fse.fixture_id=o.fixture_id
    WHERE f.kickoff_utc > ? AND f.kickoff_utc < ? AND fse.has_api_football_data=1''', (now, window)).fetchone()[0]
print(f"Fixtures with odds+enrich:   {n_both}")

n_btts = conn.execute('''SELECT COUNT(DISTINCT om.fixture_id) FROM odds_markets om
    JOIN fixtures f ON f.fixture_id=om.fixture_id
    WHERE f.kickoff_utc > ? AND om.market_key='BTTS' ''', (now,)).fetchone()[0]
print(f"Fixtures with BTTS odds:     {n_btts}")

n_ou = conn.execute('''SELECT COUNT(DISTINCT om.fixture_id) FROM odds_markets om
    JOIN fixtures f ON f.fixture_id=om.fixture_id
    WHERE f.kickoff_utc > ? AND om.market_key='OVER_UNDER' ''', (now,)).fetchone()[0]
print(f"Fixtures with O/U odds:      {n_ou}")

n_pending = conn.execute("SELECT COUNT(*) FROM model_bets WHERE status='pending'").fetchone()[0]
print(f"Current pending bets:        {n_pending}")

print()
print("League breakdown (fixtures with 1X2 odds, next 48h):")
rows = conn.execute('''SELECT fse.league_name, COUNT(DISTINCT o.fixture_id) as n
    FROM odds o
    JOIN fixtures f ON f.fixture_id=o.fixture_id
    LEFT JOIN fixture_stat_enrichment fse ON fse.fixture_id=o.fixture_id
    WHERE f.kickoff_utc > ?
    GROUP BY fse.league_name ORDER BY n DESC LIMIT 20''', (now,)).fetchall()
for r in rows:
    name = r[0] if r[0] else "(no enrichment)"
    print(f"  {name:<42} {r[1]}")

print()
print("All leagues currently in _SCAN_LEAGUES from ingestion/api_football_odds.py:")
leagues = [
    (103, 2026, "Eliteserien"),
    (104, 2026, "OBOS-ligaen"),
    (725, 2026, "Toppserien"),
    (1,   2026, "FIFA World Cup"),
    (2,   2026, "UEFA Champions League"),
    (5,   2025, "UEFA Nations League"),
    (113, 2026, "Allsvenskan"),
    (114, 2026, "Superettan"),
    (164, 2026, "Urvalsdeild Iceland"),
    (244, 2026, "Veikkausliiga Finland"),
    (357, 2026, "IRL Premier Division"),
    (358, 2026, "IRL First Division"),
    (72,  2026, "BRA Serie B"),
]
for lid, season, name in leagues:
    n = conn.execute('''SELECT COUNT(DISTINCT o.fixture_id) FROM odds o
        JOIN fixtures f ON f.fixture_id=o.fixture_id
        JOIN api_football_fixture_links lnk ON lnk.fixture_id=o.fixture_id
        WHERE f.kickoff_utc > ? AND lnk.api_football_league_id=?''', (now, lid)).fetchone()[0]
    print(f"  {name:<35} league={lid}  with_odds={n}")

conn.close()
