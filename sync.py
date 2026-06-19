"""
TippeQpongen data sync CLI.

Standard weekly flow:
  --daily          NT coupons + Pinnacle odds + AF enrichment + AF odds fallback + validate
  --refresh-coupons  force-refresh NT coupons + enrichment + AF odds fallback (start-of-week)

Usage:
    python sync.py --daily                # all-in-one: NT + odds + AF enrichment + AF odds + validate
    python sync.py --refresh-coupons      # force NT re-fetch + enrichment + AF odds fallback
    python sync.py --af-odds              # fill missing odds from API-Football (manual/debug)
    python sync.py --enrich-fixtures      # match NT fixtures to AF, store stats/form
    python sync.py --week N --year YYYY   # explicit week/year for any command
    python sync.py --seed-only            # flat-file seed only, no API calls
    python sync.py --nt-only              # NT fixture fetch only
    python sync.py --odds-only            # Pinnacle odds only (fixtures must exist)
    python sync.py --odds-snapshot        # Pinnacle odds + append timestamped snapshot
    python sync.py --mark-closing-odds    # mark last pre-kickoff snapshot as closing line
    python sync.py --status               # show DB contents for current week
    python sync.py --validate             # data integrity checks (PASS/WARN/FAIL)
    python sync.py --review               # teams/fixtures needing manual review
    python sync.py --results-status       # coupons with predictions but missing results
    python sync.py --evaluate             # compute hit rate / cover rate for all coupons
    python sync.py --nt-debug             # print raw NT API response

Environment (.env or shell):
    ODDS_API_KEY      — theoddsapi.com key for Pinnacle odds
    API_FOOTBALL_KEY  — api-sports.io key for AF enrichment and odds fallback
"""
import argparse
import sys
from datetime import datetime


def _current_week_year() -> tuple[int, int]:
    iso = datetime.now().isocalendar()
    return iso.week, iso.year


# ── Step 1: NT fixture ingestion ────────────────────────────────────────────────

def cmd_fetch_nt(week: int, year: int, debug: bool = False) -> bool:
    """Fetch fixtures from NT API. Returns True on success."""
    from db.schema import init_db
    from ingestion.norsk_tipping import ingest_game_days

    init_db()
    ok = ingest_game_days(week=week, year=year, debug=debug)
    if not ok:
        print("  nt: ingestion returned no coupons.")
    return ok


# ── Step 1b: flat-file fallback ─────────────────────────────────────────────────

def cmd_seed_flat_file(week: int, year: int) -> bool:
    """Seed from a data/coupon_weekNN_YYYY.py flat file. Returns True on success."""
    from db.schema import init_db
    from ingestion.seed import seed_from_flat_file

    init_db()
    module = f"data.coupon_week{week:02d}_{year}"
    try:
        seed_from_flat_file(module, week, year)
        return True
    except ModuleNotFoundError:
        print(
            f"  fallback: no flat-file found for week {week}/{year} ({module}.py).\n"
            f"  Create the file manually or ensure the NT API is reachable."
        )
        return False


# ── Step 2: Pinnacle odds via The Odds API ──────────────────────────────────────

def cmd_fetch_odds(week: int, year: int) -> None:
    from config import ODDS_API_KEY
    from db.coupon import list_coupons
    from ingestion.odds_api import ingest_odds_for_coupon

    if not ODDS_API_KEY:
        print("  odds: ODDS_API_KEY not set — skipping odds fetch. See .env.example.")
        return

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        print("  odds: no coupons in DB — run NT fetch first.")
        return

    for c in coupons:
        n = ingest_odds_for_coupon(c["coupon_id"])
        label = "bookmaker odds" if n else "no bookmaker matches found"
        print(f"  odds: {c['coupon_id']} — {n} fixture(s) with {label}")


# ── Status ───────────────────────────────────────────────────────────────────────

def cmd_status(week: int, year: int) -> None:
    from db.schema import init_db
    from db.coupon import list_coupons, get_coupon_matches

    init_db()
    coupons = list_coupons(week=week, year=year)
    if not coupons:
        print(f"\n  No coupons in DB for week {week}/{year}.")
        print(f"  Run: python sync.py --week {week} --year {year}\n")
        return

    print(f"\nWeek {week}/{year} — {len(coupons)} coupon(s):\n")
    for c in coupons:
        matches   = get_coupon_matches(c["coupon_id"])
        odds_srcs = {r.get("source") or "none" for r in matches}
        n_odds    = sum(1 for r in matches if r.get("odds_h") is not None)
        n_tips    = sum(1 for r in matches if r.get("expert_h") is not None
                        or r.get("public_h") is not None)
        print(f"  [{c['coupon_id']}]  {c.get('label', '')}")
        print(f"    Source:     {c.get('source', 'unknown')} / {c.get('confidence', '?')}")
        print(f"    Deadline:   {c.get('deadline_utc', '?')}")
        print(f"    Fixtures:   {len(matches)}")
        print(f"    With odds:  {n_odds}  ({', '.join(sorted(odds_srcs))})")
        print(f"    With tips:  {n_tips}  (expert/public percentages)")
        if c.get("last_synced_at"):
            print(f"    Synced:     {c['last_synced_at'][:19]}")
        print()


# ── Review ───────────────────────────────────────────────────────────────────────

def cmd_review(week: int, year: int) -> None:
    """Show teams and fixtures flagged for manual review."""
    from db.connection import get_conn
    from db.schema import init_db

    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT detail, logged_at FROM coupon_log
               WHERE event = 'new_team_needs_review'
               ORDER BY logged_at DESC LIMIT 50"""
        ).fetchall()

    if not rows:
        print("\n  No items needing review.\n")
        return

    print(f"\n  {len(rows)} team(s) needing review:\n")
    import json
    for row in rows:
        try:
            detail = json.loads(row["detail"] or "{}")
        except Exception:
            detail = {}
        print(f"  [{row['logged_at'][:10]}] {detail.get('name_local', '?')}")
        print(f"    team_id:       {detail.get('team_id', '?')}")
        print(f"    nt_team_id:    {detail.get('nt_team_id', '?')}")
        print(f"    arrangement:   {detail.get('arrangement_name', '?')}")
        print(f"    inferred:      {detail.get('inferred_gender', '?')} / "
              f"{detail.get('inferred_age_group', '?')}")
        print(f"    Fix:           UPDATE teams SET gender=?, age_group=? WHERE nt_team_id=?")
        print()


# ── Validate ─────────────────────────────────────────────────────────────────────

# First-tier sources used as the primary probability baseline.
# Fallback bookmakers from The Odds API (betsson, unibet_*, etc.) are valid
# sources — the check WARNs only if a completely unrecognised/empty string appears.
_PRIMARY_ODD_SOURCES  = {"pinnacle", "norsk_tipping", "manual"}
_KNOWN_ODD_SOURCES    = _PRIMARY_ODD_SOURCES | {
    "betsson", "unibet_se", "unibet_nl", "unibet_uk", "unibet_fr",
    "leovegas", "leovegas_se", "marathonbet", "bwin", "bet365",
    "williamhill", "nordicbet", "betfair", "betway",
    "api_football",
}


def _vresult(status: str, label: str, detail: str) -> tuple[str, str, str]:
    return (status, label, detail)


def _check_fixture_count(conn, week: int, year: int) -> tuple:
    rows = conn.execute(
        """SELECT c.coupon_id, c.source, COUNT(cf.fixture_id) AS n
           FROM coupons c
           LEFT JOIN coupon_fixtures cf ON cf.coupon_id = c.coupon_id
           WHERE c.week=? AND c.year=?
           GROUP BY c.coupon_id""",
        (week, year),
    ).fetchall()
    if not rows:
        return _vresult("WARN", "Fixture count", "No coupons found for this week")
    bad_nt = [r for r in rows if r["source"] == "nt_api" and r["n"] != 12]
    bad_manual = [r for r in rows if r["source"] != "nt_api" and r["n"] < 12]
    if bad_nt:
        names = ", ".join(f"{r['coupon_id']}({r['n']})" for r in bad_nt)
        return _vresult("FAIL", "Fixture count", f"NT coupons with wrong count: {names}")
    detail = f"{len(rows)} coupon(s) × 12 fixtures"
    if bad_manual:
        names = ", ".join(f"{r['coupon_id']}({r['n']})" for r in bad_manual)
        return _vresult("WARN", "Fixture count", f"Manual coupons with < 12: {names}")
    return _vresult("PASS", "Fixture count", detail)


def _check_nt_match_ids(conn, week: int, year: int) -> tuple:
    total = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?""",
        (week, year),
    ).fetchone()[0]
    missing_nt_api = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
             AND f.source='nt_api' AND f.nt_match_id IS NULL""",
        (week, year),
    ).fetchone()[0]
    missing_other = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
             AND (f.source IS NULL OR f.source != 'nt_api')
             AND f.nt_match_id IS NULL""",
        (week, year),
    ).fetchone()[0]
    if missing_nt_api:
        return _vresult("FAIL", "NT match IDs", f"{missing_nt_api} nt_api fixtures missing nt_match_id")
    if missing_other:
        return _vresult("WARN", "NT match IDs", f"{missing_other}/{total} manual fixtures have no nt_match_id (expected)")
    return _vresult("PASS", "NT match IDs", f"{total}/{total} present")


def _check_kickoff_times(conn, week: int, year: int) -> tuple:
    missing = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
             AND (f.kickoff_utc IS NULL OR f.kickoff_utc='')""",
        (week, year),
    ).fetchone()[0]
    total = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?""",
        (week, year),
    ).fetchone()[0]
    if missing:
        return _vresult("FAIL", "Kickoff times", f"{missing}/{total} fixtures missing kickoff_utc")
    return _vresult("PASS", "Kickoff times", f"{total}/{total} present")


def _check_day_types(conn, week: int, year: int) -> tuple:
    missing_nt = conn.execute(
        "SELECT COUNT(*) FROM coupons WHERE week=? AND year=? AND source='nt_api' AND day_type IS NULL",
        (week, year),
    ).fetchone()[0]
    missing_manual = conn.execute(
        "SELECT COUNT(*) FROM coupons WHERE week=? AND year=? AND (source IS NULL OR source!='nt_api') AND day_type IS NULL",
        (week, year),
    ).fetchone()[0]
    if missing_nt:
        return _vresult("FAIL", "Coupon day_type", f"{missing_nt} nt_api coupons missing day_type")
    if missing_manual:
        return _vresult("WARN", "Coupon day_type", f"{missing_manual} manual coupon(s) missing day_type (expected)")
    return _vresult("PASS", "Coupon day_type", "All coupons have day_type")


def _check_team_ids(conn, week: int, year: int) -> tuple:
    missing = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
             AND (f.home_team_id IS NULL OR f.away_team_id IS NULL)""",
        (week, year),
    ).fetchone()[0]
    total = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?""",
        (week, year),
    ).fetchone()[0]
    if missing:
        return _vresult("FAIL", "Team IDs", f"{missing} fixtures missing home_team_id or away_team_id")
    return _vresult("PASS", "Team IDs", f"{total * 2} home/away refs all present")


def _check_gender_review(conn) -> tuple:
    pending = conn.execute(
        """SELECT COUNT(DISTINCT json_extract(detail,'$.nt_team_id')) FROM coupon_log
           WHERE event='new_team_needs_review'""",
    ).fetchone()[0]
    if pending:
        return _vresult("WARN", "Team gender review", f"{pending} team(s) need confirmation — run --review")
    return _vresult("PASS", "Team gender review", "No teams pending review")


def _check_odds_purity(conn, week: int, year: int) -> tuple:
    rows = conn.execute(
        """SELECT o.source, COUNT(*) AS n FROM odds o
           JOIN coupon_fixtures cf ON cf.fixture_id = o.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
           GROUP BY o.source""",
        (week, year),
    ).fetchall()
    unknown = [(r["source"], r["n"]) for r in rows
               if (r["source"] or "") not in _KNOWN_ODD_SOURCES]
    non_primary = [(r["source"], r["n"]) for r in rows
                   if (r["source"] or "") in (_KNOWN_ODD_SOURCES - _PRIMARY_ODD_SOURCES)]
    if unknown:
        detail = ", ".join(f"{src}({n})" for src, n in unknown)
        return _vresult("FAIL", "Odds table purity", f"Unrecognised sources in odds: {detail}")
    total = sum(r["n"] for r in rows)
    if non_primary:
        detail = ", ".join(f"{src}({n})" for src, n in non_primary)
        return _vresult("WARN", "Odds table purity",
                        f"{total} rows ok — fallback bookmaker(s) in use: {detail}")
    return _vresult("PASS", "Odds table purity", f"All {total} odds rows have valid source")


def _check_no_dup_nt_match(conn) -> tuple:
    dups = conn.execute(
        """SELECT nt_match_id, COUNT(*) AS n FROM fixtures
           WHERE nt_match_id IS NOT NULL
           GROUP BY nt_match_id HAVING n > 1""",
    ).fetchall()
    if dups:
        detail = ", ".join(f"{r['nt_match_id']}(×{r['n']})" for r in dups)
        return _vresult("FAIL", "No duplicate nt_match_id", f"Duplicates found: {detail}")
    return _vresult("PASS", "No duplicate nt_match_id", "All nt_match_ids unique")


def _check_no_dup_cf(conn, week: int, year: int) -> tuple:
    dups = conn.execute(
        """SELECT cf.coupon_id, cf.fixture_id, COUNT(*) AS n
           FROM coupon_fixtures cf
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           WHERE c.week=? AND c.year=?
           GROUP BY cf.coupon_id, cf.fixture_id HAVING n > 1""",
        (week, year),
    ).fetchall()
    if dups:
        return _vresult("FAIL", "No duplicate junctions",
                        f"{len(dups)} (coupon_id, fixture_id) pair(s) appear more than once")
    return _vresult("PASS", "No duplicate junctions", "All coupon_fixtures rows unique")


def _check_team_integrity(conn, week: int, year: int) -> tuple:
    orphan_home = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           LEFT JOIN teams th ON th.team_id = f.home_team_id
           WHERE c.week=? AND c.year=? AND th.team_id IS NULL AND f.home_team_id IS NOT NULL""",
        (week, year),
    ).fetchone()[0]
    orphan_away = conn.execute(
        """SELECT COUNT(*) FROM fixtures f
           JOIN coupon_fixtures cf ON cf.fixture_id = f.fixture_id
           JOIN coupons c ON c.coupon_id = cf.coupon_id
           LEFT JOIN teams ta ON ta.team_id = f.away_team_id
           WHERE c.week=? AND c.year=? AND ta.team_id IS NULL AND f.away_team_id IS NOT NULL""",
        (week, year),
    ).fetchone()[0]
    if orphan_home or orphan_away:
        return _vresult("FAIL", "Team integrity",
                        f"{orphan_home} home + {orphan_away} away team_ids not in teams table")
    return _vresult("PASS", "Team integrity", "All team_ids resolve to known teams")


def _check_pred_fixture_refs(conn) -> tuple:
    orphan = conn.execute(
        """SELECT COUNT(*) FROM coupon_predictions p
           LEFT JOIN fixtures f ON f.fixture_id = p.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "Predictions/fixtures", f"{orphan} prediction(s) reference missing fixture_id")
    total = conn.execute("SELECT COUNT(*) FROM coupon_predictions").fetchone()[0]
    return _vresult("PASS", "Predictions/fixtures", f"All {total} predictions reference valid fixtures")


def _check_result_fixture_refs(conn) -> tuple:
    orphan = conn.execute(
        """SELECT COUNT(*) FROM match_results r
           LEFT JOIN fixtures f ON f.fixture_id = r.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "Results/fixtures", f"{orphan} result(s) reference missing fixture_id")
    total = conn.execute("SELECT COUNT(*) FROM match_results").fetchone()[0]
    return _vresult("PASS", "Results/fixtures", f"All {total} results reference valid fixtures")


def _check_no_dup_results(conn) -> tuple:
    dups = conn.execute(
        """SELECT fixture_id, COUNT(*) AS n FROM match_results
           GROUP BY fixture_id HAVING n > 1"""
    ).fetchall()
    if dups:
        return _vresult("FAIL", "No duplicate results",
                        f"{len(dups)} fixture(s) have multiple result rows")
    return _vresult("PASS", "No duplicate results", "All fixture results unique")


def _check_no_dup_predictions(conn) -> tuple:
    dups = conn.execute(
        """SELECT coupon_id, fixture_id, COUNT(*) AS n FROM coupon_predictions
           GROUP BY coupon_id, fixture_id HAVING n > 1"""
    ).fetchall()
    if dups:
        return _vresult("FAIL", "No duplicate predictions",
                        f"{len(dups)} (coupon_id, fixture_id) pair(s) appear more than once")
    return _vresult("PASS", "No duplicate predictions", "All predictions unique")


def _check_snapshot_fixture_refs(conn) -> tuple:
    orphan = conn.execute(
        """SELECT COUNT(*) FROM odds_snapshots s
           LEFT JOIN fixtures f ON f.fixture_id = s.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "Snapshots/fixtures", f"{orphan} snapshot(s) reference missing fixture_id")
    total = conn.execute("SELECT COUNT(*) FROM odds_snapshots").fetchone()[0]
    return _vresult("PASS", "Snapshots/fixtures", f"All {total} snapshots reference valid fixtures")


def _check_no_dup_snapshots(conn) -> tuple:
    dups = conn.execute(
        """SELECT fixture_id, bookmaker, market, fetched_at, COUNT(*) AS n
           FROM odds_snapshots
           GROUP BY fixture_id, bookmaker, market, fetched_at
           HAVING n > 1"""
    ).fetchall()
    if dups:
        return _vresult("FAIL", "No duplicate snapshots",
                        f"{len(dups)} (fixture, bookmaker, market, time) duplicate(s)")
    return _vresult("PASS", "No duplicate snapshots", "All snapshots unique")


def _check_one_closing_per_fixture(conn) -> tuple:
    multi = conn.execute(
        """SELECT fixture_id, bookmaker, market, COUNT(*) AS n
           FROM odds_snapshots
           WHERE is_closing_snapshot=1
           GROUP BY fixture_id, bookmaker, market
           HAVING n > 1"""
    ).fetchall()
    if multi:
        return _vresult("FAIL", "Single closing snapshot",
                        f"{len(multi)} fixture(s) have multiple closing snapshots")
    n_closing = conn.execute(
        "SELECT COUNT(*) FROM odds_snapshots WHERE is_closing_snapshot=1"
    ).fetchone()[0]
    return _vresult("PASS", "Single closing snapshot", f"{n_closing} closing snapshot(s), all unique")


# Phase 4B validation checks

def _check_enrichment_fixture_refs(conn) -> tuple:
    orphan = conn.execute(
        """SELECT COUNT(*) FROM fixture_stat_enrichment e
           LEFT JOIN fixtures f ON f.fixture_id = e.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "Enrichment/fixtures",
                        f"{orphan} enrichment row(s) reference missing fixture_id")
    n = conn.execute("SELECT COUNT(*) FROM fixture_stat_enrichment").fetchone()[0]
    return _vresult("PASS", "Enrichment/fixtures", f"All {n} enrichment rows reference valid fixtures")


def _check_af_link_fixture_refs(conn) -> tuple:
    orphan = conn.execute(
        """SELECT COUNT(*) FROM api_football_fixture_links lnk
           LEFT JOIN fixtures f ON f.fixture_id = lnk.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "AF links/fixtures",
                        f"{orphan} AF link(s) reference missing fixture_id")
    n = conn.execute("SELECT COUNT(*) FROM api_football_fixture_links").fetchone()[0]
    return _vresult("PASS", "AF links/fixtures", f"All {n} AF links reference valid fixtures")


def _check_no_dup_af_fixture_id(conn) -> tuple:
    dups = conn.execute(
        """SELECT api_football_fixture_id, COUNT(*) AS n
           FROM api_football_fixture_links
           GROUP BY api_football_fixture_id HAVING n > 1"""
    ).fetchall()
    if dups:
        ids = ", ".join(str(r["api_football_fixture_id"]) for r in dups)
        return _vresult("FAIL", "No dup AF fixture IDs",
                        f"api_football_fixture_id not unique: {ids}")
    return _vresult("PASS", "No dup AF fixture IDs", "All AF fixture IDs unique")


def _check_confidence_range(conn) -> tuple:
    bad = conn.execute(
        """SELECT COUNT(*) FROM api_football_fixture_links
           WHERE match_confidence < 0 OR match_confidence > 1"""
    ).fetchone()[0]
    if bad:
        return _vresult("FAIL", "Confidence range",
                        f"{bad} link(s) with confidence outside [0,1]")
    mn = conn.execute(
        "SELECT MIN(match_confidence) FROM api_football_fixture_links"
    ).fetchone()[0]
    mx = conn.execute(
        "SELECT MAX(match_confidence) FROM api_football_fixture_links"
    ).fetchone()[0]
    if mn is None:
        return _vresult("PASS", "Confidence range", "No links yet")
    return _vresult("PASS", "Confidence range",
                    f"All in [0,1]  min={mn:.2f}  max={mx:.2f}")


def _check_enrichment_data_flag(conn) -> tuple:
    bad = conn.execute(
        """SELECT COUNT(*) FROM fixture_stat_enrichment
           WHERE has_api_football_data = 1
             AND api_football_fixture_id IS NULL"""
    ).fetchone()[0]
    if bad:
        return _vresult("FAIL", "Enrichment data flag",
                        f"{bad} row(s) have has_api_football_data=1 but no fixture_id")
    n = conn.execute(
        "SELECT COUNT(*) FROM fixture_stat_enrichment WHERE has_api_football_data=1"
    ).fetchone()[0]
    return _vresult("PASS", "Enrichment data flag",
                    f"{n} enriched fixture(s) all have valid AF fixture_id")


def _check_estimated_prior_integrity(conn, week: int, year: int) -> tuple:
    """
    Validate fixture_estimated_prior rows:
    1. Priors must sum to ~100% (within ±2pp)
    2. Priors must NOT exist for fixtures that already have bookmaker odds
    3. All prior rows must reference a valid fixture_id
    """
    # Check sum within tolerance
    bad_sum = conn.execute(
        """SELECT COUNT(*) FROM fixture_estimated_prior
           WHERE ABS(estimated_h + estimated_u + estimated_b - 1.0) > 0.02"""
    ).fetchone()[0]
    if bad_sum:
        return _vresult("FAIL", "Estimated prior sum",
                        f"{bad_sum} prior(s) do not sum to ~100%")

    # Check no overlap with fixtures that have bookmaker odds
    overlap = conn.execute(
        """SELECT COUNT(*) FROM fixture_estimated_prior ep
           JOIN odds o ON o.fixture_id = ep.fixture_id
           WHERE o.source IN ('pinnacle','norsk_tipping','manual','api_football')"""
    ).fetchone()[0]
    if overlap:
        return _vresult("FAIL", "Estimated prior purity",
                        f"{overlap} estimated prior(s) exist for fixtures with bookmaker odds")

    # Check fixture references are valid
    orphan = conn.execute(
        """SELECT COUNT(*) FROM fixture_estimated_prior ep
           LEFT JOIN fixtures f ON f.fixture_id = ep.fixture_id
           WHERE f.fixture_id IS NULL"""
    ).fetchone()[0]
    if orphan:
        return _vresult("FAIL", "Estimated prior/fixtures",
                        f"{orphan} estimated prior(s) reference missing fixture_id")

    n = conn.execute("SELECT COUNT(*) FROM fixture_estimated_prior").fetchone()[0]
    if n == 0:
        return _vresult("PASS", "Estimated priors", "None computed yet")
    return _vresult("PASS", "Estimated priors",
                    f"{n} row(s) valid — no overlap with bookmaker odds")


def _check_evaluation_completeness(conn) -> tuple:
    bad = conn.execute(
        """SELECT e.coupon_id, COUNT(r.result_id) AS n_results
           FROM coupon_evaluations e
           JOIN coupon_predictions p ON p.coupon_id = e.coupon_id
           LEFT JOIN match_results r ON r.fixture_id = p.fixture_id
           WHERE e.evaluation_status = 'complete'
           GROUP BY e.coupon_id
           HAVING n_results < e.total_fixtures"""
    ).fetchall()
    if bad:
        names = ", ".join(r["coupon_id"] for r in bad)
        return _vresult("FAIL", "Evaluation completeness",
                        f"'complete' status but <total_fixtures results: {names}")
    total = conn.execute(
        "SELECT COUNT(*) FROM coupon_evaluations WHERE evaluation_status='complete'"
    ).fetchone()[0]
    return _vresult("PASS", "Evaluation completeness", f"{total} complete evaluation(s) all consistent")


def cmd_validate(week: int, year: int) -> None:
    from db.schema import init_db
    from db.connection import get_conn

    init_db()
    conn = get_conn()

    checks = [
        _check_fixture_count(conn, week, year),
        _check_nt_match_ids(conn, week, year),
        _check_kickoff_times(conn, week, year),
        _check_day_types(conn, week, year),
        _check_team_ids(conn, week, year),
        _check_gender_review(conn),
        _check_odds_purity(conn, week, year),
        _check_no_dup_nt_match(conn),
        _check_no_dup_cf(conn, week, year),
        _check_team_integrity(conn, week, year),
        # Phase 2 checks
        _check_pred_fixture_refs(conn),
        _check_result_fixture_refs(conn),
        _check_no_dup_results(conn),
        _check_no_dup_predictions(conn),
        _check_evaluation_completeness(conn),
        # Phase 3 checks
        _check_snapshot_fixture_refs(conn),
        _check_no_dup_snapshots(conn),
        _check_one_closing_per_fixture(conn),
        # Phase 4B checks
        _check_enrichment_fixture_refs(conn),
        _check_af_link_fixture_refs(conn),
        _check_no_dup_af_fixture_id(conn),
        _check_confidence_range(conn),
        _check_enrichment_data_flag(conn),
        # Estimated priors
        _check_estimated_prior_integrity(conn, week, year),
    ]

    print(f"\nTippeQpongen validate — week {week}/{year}\n")

    labels = {
        "PASS": "[ PASS ]",
        "WARN": "[ WARN ]",
        "FAIL": "[ FAIL ]",
    }
    n_pass = n_warn = n_fail = 0
    for i, (status, label, detail) in enumerate(checks, 1):
        tag = labels[status]
        print(f"  {tag} Check {i:2d}: {label:<22} {detail}")
        if status == "PASS":
            n_pass += 1
        elif status == "WARN":
            n_warn += 1
        else:
            n_fail += 1

    print()
    if n_fail:
        print(f"  Result: FAIL — {n_fail} critical issue(s), {n_warn} warning(s).")
        print("  Fix failures before relying on this week's data.\n")
        sys.exit(1)
    elif n_warn:
        print(f"  Result: PASS with {n_warn} warning(s).")
        if n_warn > 0:
            print("  Run `python sync.py --review` for details.\n")
    else:
        print(f"  Result: PASS — all {n_pass} checks clean.\n")


# ── Results status ───────────────────────────────────────────────────────────────

def cmd_results_status() -> None:
    from db.schema import init_db
    from db.history import list_coupons_with_predictions

    init_db()
    coupons = list_coupons_with_predictions()
    if not coupons:
        print("\n  No coupons with saved predictions found.")
        print("  Save a coupon via the Streamlit app first (click 'Lagre kupong').\n")
        return

    _day = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}
    print("\nTippeQpongen results status\n")
    for c in coupons:
        dtype = _day.get(c.get("day_type", ""), c.get("day_type", "?"))
        n_p = c["n_predictions"]
        n_r = c["n_results"]
        if n_r == n_p:
            flag = "✓ complete"
        elif n_r > 0:
            flag = f"⚑ partial ({n_p - n_r} missing)"
        else:
            flag = "✗ no results"
        print(f"  [{c['coupon_id']}]  {dtype}  —  {n_p} predictions, {n_r} results  {flag}")
    print()


# ── Evaluate ──────────────────────────────────────────────────────────────────────

def cmd_evaluate() -> None:
    from db.schema import init_db
    from db.history import list_coupons_with_predictions, save_evaluation
    from db.coupon import list_coupons

    init_db()
    coupons_with_preds = list_coupons_with_predictions()
    if not coupons_with_preds:
        print("\n  No coupons with saved predictions found.\n")
        return

    # Build total_rows map from coupons table via coupon_evaluations or a default
    # Use total_rows = 1 as placeholder when not stored; snap from predictions
    from db.connection import get_conn
    conn = get_conn()

    _day = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}
    print("\nTippeQpongen evaluate\n")

    for c in coupons_with_preds:
        if c["n_results"] == 0:
            print(f"  [{c['coupon_id']}]  no results yet — skipping")
            continue

        # Estimate total_rows from coupon (if evaluations already have it, use that)
        existing_ev = conn.execute(
            "SELECT total_rows, stake_nok FROM coupon_evaluations WHERE coupon_id=?",
            (c["coupon_id"],),
        ).fetchone()
        if existing_ev:
            total_rows = existing_ev["total_rows"]
            stake_nok  = existing_ev["stake_nok"]
        else:
            total_rows = 192   # default to most common budget
            stake_nok  = 192.0

        ev = save_evaluation(c["coupon_id"], total_rows, stake_nok)
        dtype = _day.get(c.get("day_type", ""), c.get("day_type", "?"))
        status = ev.get("evaluation_status", "?")
        n_r    = ev.get("n_results", "?")
        n_t    = ev.get("total_fixtures", 12)
        corr   = ev.get("correct_picks", "?")
        hit    = f"{ev['hit_rate']*100:.1f}%" if ev.get("hit_rate") is not None else "?"
        cov    = f"{ev['cover_rate']*100:.1f}%" if ev.get("cover_rate") is not None else "?"
        all12  = "Yes" if ev.get("all_12_correct") else "No"
        print(
            f"  [{c['coupon_id']}]  {dtype}  {n_r}/{n_t} results  "
            f"status: {status}  correct: {corr}/{n_t} ({hit})  "
            f"covered: {cov}  all_12: {all12}"
        )
    print()


# ── Odds snapshot ────────────────────────────────────────────────────────────────

def cmd_odds_snapshot(week: int, year: int) -> None:
    """
    Fetch current Pinnacle odds for all coupon fixtures in the given week
    and append a timestamped snapshot to odds_snapshots.
    """
    from config import ODDS_API_KEY
    from db.schema import init_db
    from db.coupon import list_coupons
    from ingestion.odds_api import ingest_odds_for_coupon

    init_db()

    if not ODDS_API_KEY:
        print("  ODDS_API_KEY not set -- skipping. See .env.example.")
        return

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        print(f"  No coupons in DB for week {week}/{year}.")
        return

    for c in coupons:
        n = ingest_odds_for_coupon(c["coupon_id"], write_snapshot=True)
        print(f"  {c['coupon_id']}: {n} fixture(s) snapshotted (Pinnacle)")


# ── Mark closing odds ─────────────────────────────────────────────────────────────

def cmd_mark_closing_odds() -> None:
    """
    For every fixture with snapshots, mark the last snapshot before kickoff
    as the closing snapshot. Run this after kickoff time has passed.
    """
    from db.schema import init_db
    from db.odds_movement import mark_all_closing

    init_db()
    n = mark_all_closing(bookmaker="pinnacle", market="h2h")
    print(f"  Closing odds marked for {n} fixture(s).")


# ── Refresh coupons ──────────────────────────────────────────────────────────────

def cmd_refresh_coupons(week: int, year: int) -> None:
    """
    Fetch live NT coupons and replace the active coupons for this week.

    - Queries the NT API for the current published coupons.
    - If new data is returned, clears stale coupon_fixtures and re-inserts.
    - Historical coupon_predictions are never modified.
    - Runs validation and prints a clear summary.
    """
    from db.schema import init_db
    from db.coupon import list_coupons, get_coupon_matches
    from ingestion.norsk_tipping import ingest_game_days

    init_db()

    before_coupons = list_coupons(week=week, year=year)
    before = {c["coupon_id"]: len(get_coupon_matches(c["coupon_id"]))
              for c in before_coupons}

    print(f"  Fetching live NT coupons for week {week}/{year}...")
    ok = ingest_game_days(week=week, year=year, force_refresh=True)

    if not ok:
        print(
            f"\n  NT returned no coupons for week {week}/{year}.\n"
            "  Coupons may not be published yet. Try again later.\n"
            "  Alternative: python sync.py --seed-only\n"
        )
        sys.exit(1)

    after_coupons = list_coupons(week=week, year=year)

    print()
    print(f"  -- Coupon refresh -- week {week}/{year} " + "-" * 28)
    for c in after_coupons:
        matches = get_coupon_matches(c["coupon_id"])
        n_now   = len(matches)
        n_odds  = sum(1 for r in matches if r.get("odds_h") is not None)
        was_new = c["coupon_id"] not in before
        tag     = "NEW" if was_new else ("UPD" if before.get(c["coupon_id"], 0) != n_now else " OK")
        src     = c.get("source", "?")
        deadline = (c.get("deadline_utc") or "")[:16]
        print(
            f"  [{tag}] {c['coupon_id']:<26}  "
            f"{n_now:2d} fixtures  {n_odds:2d} with odds  "
            f"src={src}  frist={deadline}"
        )
    print()

    # Validation summary
    from db.connection import get_conn
    conn = get_conn()
    checks = [
        _check_fixture_count(conn, week, year),
        _check_nt_match_ids(conn, week, year),
        _check_kickoff_times(conn, week, year),
        _check_day_types(conn, week, year),
        _check_team_ids(conn, week, year),
        _check_gender_review(conn),
        _check_odds_purity(conn, week, year),
        _check_no_dup_nt_match(conn),
        _check_no_dup_cf(conn, week, year),
        _check_team_integrity(conn, week, year),
    ]
    n_fail = sum(1 for s, _, _ in checks if s == "FAIL")
    n_warn = sum(1 for s, _, _ in checks if s == "WARN")
    if n_fail:
        val_line = f"FAIL — {n_fail} issue(s)"
        for s, lbl, det in checks:
            if s == "FAIL":
                print(f"    FAIL: {lbl}: {det}")
    elif n_warn:
        val_line = f"PASS with {n_warn} warning(s)"
    else:
        val_line = "PASS — all checks clean"
    print(f"  Validation:  {val_line}")
    print()

    # ── Enrichment + AF odds fallback ─────────────────────────────────────────
    from config import API_FOOTBALL_KEY
    if API_FOOTBALL_KEY:
        print("  Running fixture enrichment + AF odds fallback...")
        try:
            from ingestion.enrich_fixtures import enrich_active_fixtures
            esummary = enrich_active_fixtures(
                week=week, year=year, verbose=True, skip_already_enriched=True
            )
            n_enr = esummary.get("n_stored", 0) if "error" not in esummary else 0
            print(f"  Enrichment: {n_enr} fixture(s) enriched/updated.")
        except Exception as exc:
            print(f"  Enrichment error: {exc}")
        try:
            from ingestion.api_football_odds import ingest_af_odds_fallback
            osummary = ingest_af_odds_fallback(week=week, year=year, verbose=True)
            n_fill = osummary.get("n_filled", 0) if "error" not in osummary else 0
            print(f"  AF odds: {n_fill} fixture(s) filled.")
        except Exception as exc:
            print(f"  AF odds error: {exc}")
        print()
    else:
        print("  API_FOOTBALL_KEY not set — skipping enrichment and AF odds.")
        print("  Set API_FOOTBALL_KEY in .env to enable automatic odds fallback.")
        print()

    print("  Run `streamlit run app.py` to see the updated coupons.")
    print()


# ── Daily sync ───────────────────────────────────────────────────────────────

def cmd_daily(week: int, year: int) -> None:
    """
    Safe all-in-one daily sync:
      1. Fetch/update NT coupons if available
      2. Fetch latest Pinnacle odds + snapshots
      3. Enrich fixtures from API-Football (stats, form, standings)
      4. Fill missing odds from API-Football fallback
      5. Run validation checks and print a summary

    Does NOT mark closing odds — run --mark-closing-odds manually after kickoff.
    """
    from db.schema import init_db
    from db.coupon import list_coupons, get_coupon_matches
    from db.connection import get_conn
    from config import ODDS_API_KEY, API_FOOTBALL_KEY

    init_db()

    # ── Step 1: NT coupons ────────────────────────────────────────────────────
    print(f"  [1/5] Fetching NT coupons for week {week}/{year}...")
    nt_ok = False
    try:
        from ingestion.norsk_tipping import ingest_game_days
        nt_ok = ingest_game_days(week=week, year=year)
    except Exception as exc:
        print(f"        NT error: {exc}")
    if nt_ok:
        print("        Done.")
    else:
        print("        NT unavailable or no new data — using existing DB data.")

    # Count coupons + fixtures after NT step
    coupons = list_coupons(week=week, year=year)
    n_coupons = len(coupons)
    n_fixtures = sum(len(get_coupon_matches(c["coupon_id"])) for c in coupons)

    if not coupons:
        print(f"\n  No coupons in DB for week {week}/{year}. Nothing to sync.\n")
        return

    # ── Step 2: Pinnacle odds + snapshots ──────────────────────────────────────
    print("  [2/5] Fetching Pinnacle odds and saving snapshots...")
    n_odds = 0
    n_snaps_new = 0
    if not ODDS_API_KEY:
        print("        ODDS_API_KEY not set — skipping. See .env.example.")
    else:
        from ingestion.odds_api import ingest_odds_for_coupon
        with get_conn() as conn:
            snaps_before = conn.execute(
                "SELECT COUNT(*) FROM odds_snapshots"
            ).fetchone()[0]
        for c in coupons:
            n_odds += ingest_odds_for_coupon(c["coupon_id"], write_snapshot=True)
        with get_conn() as conn:
            snaps_after = conn.execute(
                "SELECT COUNT(*) FROM odds_snapshots"
            ).fetchone()[0]
        n_snaps_new = snaps_after - snaps_before
        print("        Done.")

    # ── Step 3: API-Football fixture enrichment ───────────────────────────────
    print("  [3/5] Enriching fixtures from API-Football (stats/form)...")
    n_enriched = 0
    enrich_skipped = 0
    if not API_FOOTBALL_KEY:
        print("        API_FOOTBALL_KEY not set — skipping enrichment.")
    else:
        try:
            from ingestion.enrich_fixtures import enrich_active_fixtures
            esummary = enrich_active_fixtures(
                week=week, year=year, verbose=False, skip_already_enriched=True
            )
            if "error" not in esummary:
                n_enriched     = esummary.get("n_stored", 0)
                enrich_skipped = esummary.get("n_skipped", 0)
                if n_enriched == 0 and esummary.get("n_attempted", 0) == 0:
                    print("        All fixtures already enriched.")
                else:
                    print(f"        Done — {n_enriched} enriched, {enrich_skipped} skipped (not_covered).")
        except Exception as exc:
            print(f"        Enrichment error: {exc}")

    # ── Step 4: API-Football odds fallback ────────────────────────────────────
    print("  [4/5] Fetching AF odds fallback for fixtures without odds...")
    n_af_filled = 0
    if not API_FOOTBALL_KEY:
        print("        API_FOOTBALL_KEY not set — skipping AF odds.")
    else:
        try:
            from ingestion.api_football_odds import ingest_af_odds_fallback
            osummary = ingest_af_odds_fallback(week=week, year=year, verbose=False)
            if "error" not in osummary:
                n_af_filled = osummary.get("n_filled", 0)
                n_af_skip   = osummary.get("n_already_have", 0)
                if n_af_filled == 0 and n_af_skip == osummary.get("n_total", 0):
                    print("        All fixtures already have odds.")
                else:
                    print(
                        f"        Done — {n_af_filled} filled via AF"
                        f", {n_af_skip} already had odds."
                    )
        except Exception as exc:
            print(f"        AF odds error: {exc}")

    # ── Step 4b: Model-estimated priors for fixtures still without odds ────────
    print("  [4b]  Computing model-estimated priors for no-odds fixtures...")
    n_est_computed = 0
    try:
        est_summary = cmd_estimated_priors(week=week, year=year, verbose=False)
        n_est_computed = est_summary.get("n_computed", 0)
        n_est_skip_odds = est_summary.get("n_skipped_has_odds", 0)
        if n_est_computed == 0:
            print("        All no-odds fixtures already estimated or no signals.")
        else:
            print(f"        Done — {n_est_computed} estimated prior(s) computed.")
    except Exception as exc:
        print(f"        Estimated priors error: {exc}")

    # ── Step 5: Validation ────────────────────────────────────────────────────
    print("  [5/5] Running validation...")
    conn = get_conn()
    checks = [
        _check_fixture_count(conn, week, year),
        _check_nt_match_ids(conn, week, year),
        _check_kickoff_times(conn, week, year),
        _check_day_types(conn, week, year),
        _check_team_ids(conn, week, year),
        _check_gender_review(conn),
        _check_odds_purity(conn, week, year),
        _check_no_dup_nt_match(conn),
        _check_no_dup_cf(conn, week, year),
        _check_team_integrity(conn, week, year),
        _check_pred_fixture_refs(conn),
        _check_result_fixture_refs(conn),
        _check_no_dup_results(conn),
        _check_no_dup_predictions(conn),
        _check_evaluation_completeness(conn),
        _check_snapshot_fixture_refs(conn),
        _check_no_dup_snapshots(conn),
        _check_one_closing_per_fixture(conn),
        # Phase 4B checks
        _check_enrichment_fixture_refs(conn),
        _check_af_link_fixture_refs(conn),
        _check_no_dup_af_fixture_id(conn),
        _check_confidence_range(conn),
        _check_enrichment_data_flag(conn),
        _check_estimated_prior_integrity(conn, week, year),
    ]
    n_pass = sum(1 for s, _, _ in checks if s == "PASS")
    n_warn = sum(1 for s, _, _ in checks if s == "WARN")
    n_fail = sum(1 for s, _, _ in checks if s == "FAIL")
    if n_fail:
        val_tag = "FAIL"
    elif n_warn:
        val_tag = f"PASS  ({n_warn} warning(s))"
    else:
        val_tag = f"PASS  (all {n_pass} checks clean)"
    print("        Done.")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"  -- Daily sync complete -- week {week}/{year} " + "-" * 26)
    print(f"  Coupons found:          {n_coupons}")
    print(f"  Fixtures:               {n_fixtures}")
    print(f"  Pinnacle odds updated:  {n_odds}  fixture(s) matched")
    print(f"  Snapshots created:      {n_snaps_new}  new  (duplicates silently skipped)")
    print(f"  AF enriched:            {n_enriched}  new fixture(s)")
    print(f"  AF odds fallback:       {n_af_filled}  fixture(s) filled  (source=api_football)")
    print(f"  Est. priors computed:   {n_est_computed}  no-odds fixture(s)")
    print(f"  Validation:             {val_tag}")
    if n_fail:
        print()
        for status, label, detail in checks:
            if status == "FAIL":
                print(f"    FAIL — {label}: {detail}")
        print()
        print("  Fix failures before relying on this week's data.")
    print()


# ── Phase 4B: enrich fixtures ────────────────────────────────────────────────

def cmd_enrich_fixtures(week: int, year: int) -> None:
    """
    Match all active NT fixtures to API-Football, fetch statistical
    enrichment (standings, form, goals), and persist to the DB.
    AF predictions are NOT fetched — use as data source only.
    """
    from db.schema import init_db
    from ingestion.enrich_fixtures import enrich_active_fixtures

    init_db()
    print(f"  Enriching fixtures for week {week}/{year}...\n")

    summary = enrich_active_fixtures(week=week, year=year, verbose=True)

    if "error" in summary:
        print(f"\n  {summary['error']}\n")
        return

    n_total   = summary["n_total"]
    n_skip    = summary["n_skipped"]
    n_att     = summary["n_attempted"]
    n_match   = summary["n_matched"]
    n_store   = summary["n_stored"]
    n_fail    = summary["n_failed"]
    avg_conf  = summary["avg_confidence"]

    print()
    print(f"  -- Enrichment summary -- week {week}/{year} " + "-" * 26)
    print(f"  Total NT fixtures:          {n_total}")
    print(f"  Skipped (not in AF):        {n_skip}")
    print(f"  Attempted:                  {n_att}")
    print(f"  Matched:                    {n_match}  / {n_att}")
    print(f"  Stored (enriched):          {n_store}")
    print(f"  Failed / no match:          {n_fail}")
    if n_match:
        print(f"  Average match confidence:   {avg_conf:.2f}")
    print()
    print("  Run `streamlit run app.py` and visit the Statistikk page to inspect.")
    print()


# ── API-Football odds fallback ───────────────────────────────────────────────

def cmd_af_odds(week: int, year: int) -> None:
    """
    Fetch API-Football odds for all active fixtures that have no existing odds.

    - Skips fixtures that already have any odds row (any source).
    - Skips fixtures with no api_football_fixture_links entry.
    - Inserts with source='api_football' for remaining fixtures.
    - Safe to run repeatedly — existing odds are never overwritten.
    """
    from db.schema import init_db
    from ingestion.api_football_odds import ingest_af_odds_fallback

    init_db()
    print(f"  Fetching AF odds fallback for week {week}/{year}...\n")

    summary = ingest_af_odds_fallback(week=week, year=year, verbose=True)

    if "error" in summary:
        print(f"\n  {summary['error']}\n")
        return

    print()
    print(f"  -- AF odds fallback summary -- week {week}/{year} " + "-" * 16)
    print(f"  Total fixtures checked:  {summary['n_total']}")
    print(f"  Already had odds:        {summary['n_already_have']}  (skipped)")
    print(f"  No AF link:              {summary['n_no_af_link']}  (skipped)")
    print(f"  Odds inserted:           {summary['n_filled']}  (source=api_football)")
    print(f"  AF has no 1X2 data:      {summary['n_no_odds_data']}")
    print(f"  Errors:                  {summary['n_failed']}")
    print()


# ── Model-estimated priors ──────────────────────────────────────────────────

def cmd_estimated_priors(week: int, year: int, verbose: bool = True) -> dict:
    """
    Compute model-estimated H/U/B priors for all fixtures in the week that
    have no bookmaker odds but do have statistical enrichment data.

    Stores results in fixture_estimated_prior (source='model_estimated').
    Never writes to the odds or odds_snapshots tables.
    Never overwrites a fixture that already has bookmaker odds.
    """
    from db.schema import init_db
    from db.connection import get_conn
    from db.coupon import list_coupons, get_coupon_matches
    from db.enrichment import get_coupon_enrichment, upsert_estimated_prior
    from analysis.estimated_prior import compute_estimated_prior

    init_db()

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        if verbose:
            print(f"  No coupons in DB for week {week}/{year}.")
        return {"n_total": 0, "n_computed": 0, "n_skipped_has_odds": 0, "n_no_signals": 0}

    # Collect unique fixtures across all coupons
    seen: set[str] = set()
    all_fixtures: list[dict] = []
    for c in coupons:
        for f in get_coupon_enrichment(c["coupon_id"]):
            fid = f["fixture_id"]
            if fid not in seen:
                seen.add(fid)
                all_fixtures.append(f)

    n_total = len(all_fixtures)
    n_computed = n_skipped_has_odds = n_no_signals = 0

    for f in all_fixtures:
        home = f.get("home_name", "?")
        away = f.get("away_name", "?")
        label = f"{home} vs {away}"

        if f.get("odds_h") is not None:
            n_skipped_has_odds += 1
            if verbose:
                print(f"  [SKIP] {label:<44}  (has bookmaker odds)")
            continue

        prior = compute_estimated_prior(f)
        if prior is None:
            n_no_signals += 1
            if verbose:
                print(f"  [NONE] {label:<44}  (no signals available)")
            continue

        upsert_estimated_prior(
            fixture_id=f["fixture_id"],
            estimated_h=prior["estimated_h"],
            estimated_u=prior["estimated_u"],
            estimated_b=prior["estimated_b"],
            signals_used=prior["signals_used"],
            confidence=prior["confidence"],
        )
        n_computed += 1
        if verbose:
            h = round(prior["estimated_h"] * 100)
            u = round(prior["estimated_u"] * 100)
            b = round(prior["estimated_b"] * 100)
            sigs = ", ".join(prior["signals_used"])
            print(
                f"  [OK]   {label:<44}  "
                f"H={h}% U={u}% B={b}%  "
                f"conf={prior['confidence']:.2f}  [{sigs}]"
            )

    return {
        "n_total":             n_total,
        "n_computed":          n_computed,
        "n_skipped_has_odds":  n_skipped_has_odds,
        "n_no_signals":        n_no_signals,
    }


# ── API-Football coverage probe ───────────────────────────────────────────────

def cmd_api_football_coverage(week: int, year: int) -> None:
    """
    For every active NT fixture in the given week, probe API-Football for:
      - fixture match (can we find this game in AF?)
      - standings availability
      - team statistics + form
      - predictions

    Prints a per-fixture coverage table and a summary.
    """
    from collections import defaultdict
    from datetime import date, timedelta

    from config import API_FOOTBALL_KEY
    from db.schema import init_db
    from db.coupon import list_coupons, get_coupon_matches
    from ingestion.api_football import (
        get_fixtures, get_standings, get_team_statistics, get_predictions,
        translate_team_name, map_nt_competition, _norm,
    )

    init_db()

    if not API_FOOTBALL_KEY:
        print("  API_FOOTBALL_KEY not set — cannot run coverage probe. See .env.example.")
        return

    coupons = list_coupons(week=week, year=year)
    if not coupons:
        print(f"\n  No coupons in DB for week {week}/{year}.\n")
        return

    # ── Collect all NT fixtures ──────────────────────────────────────────────
    all_nt: list[dict] = []
    for c in coupons:
        day_label = c["coupon_id"].split("-")[0].upper()   # MIDTUKE / LORDAG / SONDAG
        for m in get_coupon_matches(c["coupon_id"]):
            ko = m.get("kickoff_utc", "")
            all_nt.append({
                "coupon":      day_label,
                "num":         m["match_number"],
                "arrangement": m.get("arrangement_name") or m.get("competition_id") or "",
                "home":        m["home_name"],
                "away":        m["away_name"],
                "kickoff":     ko[:16],
                "kick_date":   ko[:10],  # YYYY-MM-DD (may be local time)
            })

    # ── Group by (af_league_id, season, kick_date) to batch AF calls ─────────
    # Include kick_date - 1 day in the range to handle CEST → UTC edge cases
    # (e.g. NT midnight CEST = prev day UTC)
    BucketKey = tuple  # (lid, season, from_date, to_date, status)

    def _bucket(f: dict) -> BucketKey:
        lid, season, status = map_nt_competition(f["arrangement"])
        kd = f["kick_date"]
        if kd and len(kd) == 10:
            try:
                d = date.fromisoformat(kd)
                from_d = (d - timedelta(days=1)).isoformat()
                to_d = kd
            except ValueError:
                from_d = to_d = kd
        else:
            from_d = to_d = kd
        return (lid, season, from_d, to_d, status)

    buckets: dict[BucketKey, list[dict]] = defaultdict(list)
    for f in all_nt:
        buckets[_bucket(f)].append(f)

    # ── Per-bucket AF lookups ────────────────────────────────────────────────
    # Cache: af fixtures per (lid, season, from, to)
    af_fix_cache:       dict[tuple, list[dict]] = {}
    # Cache: standings available per (lid, season)
    standings_cache:    dict[tuple, bool]       = {}
    # Cache: team stats available per (lid, season) — sampled from first matched team
    teamstats_cache:    dict[tuple, bool]       = {}

    results: list[dict] = []

    for bkey, fixtures in sorted(buckets.items(), key=lambda kv: (kv[0][4], kv[0][0] or 0)):
        lid, season, from_d, to_d, status = bkey

        if status in ("not_covered",):
            for f in fixtures:
                results.append({**f,
                    "af_league_id": None, "af_fixture_id": None,
                    "home_matched": False, "away_matched": False,
                    "has_standings": False, "has_team_stats": False,
                    "has_form": False, "has_predictions": False,
                    "coverage": "not_covered",
                })
            continue

        if lid is None:
            for f in fixtures:
                results.append({**f,
                    "af_league_id": None, "af_fixture_id": None,
                    "home_matched": False, "away_matched": False,
                    "has_standings": False, "has_team_stats": False,
                    "has_form": False, "has_predictions": False,
                    "coverage": "league_not_mapped",
                })
            continue

        # Fetch AF fixtures for this league + date range
        fix_cache_key = (lid, season, from_d, to_d)
        if fix_cache_key not in af_fix_cache:
            try:
                af_fix_cache[fix_cache_key] = get_fixtures(
                    league_id=lid, season=season, from_date=from_d, to_date=to_d
                )
            except Exception as exc:
                print(f"  [WARN] AF fixtures fetch failed for league {lid}: {exc}")
                af_fix_cache[fix_cache_key] = []
        af_fixtures = af_fix_cache[fix_cache_key]

        # Check standings (once per league/season)
        stand_key = (lid, season)
        if stand_key not in standings_cache:
            try:
                stand_resp = get_standings(lid, season)
                standings_cache[stand_key] = bool(stand_resp)
            except Exception:
                standings_cache[stand_key] = False
        has_standings = standings_cache[stand_key]

        # Match each NT fixture to an AF fixture
        sampled_team_stats = False  # check team stats once per bucket

        def _names_match(a: str, b: str) -> bool:
            return a == b or a in b or b in a

        for f in fixtures:
            # Translate both NT and AF names to a common normalized form
            home_en = translate_team_name(f["home"])   # already _norm'd by translate_team_name
            away_en = translate_team_name(f["away"])

            matched_af = None
            for af in af_fixtures:
                af_home_raw = af.get("teams", {}).get("home", {}).get("name", "")
                af_away_raw = af.get("teams", {}).get("away", {}).get("name", "")
                af_home = translate_team_name(af_home_raw)  # handles Turkiye→turkey etc.
                af_away = translate_team_name(af_away_raw)
                if _names_match(home_en, af_home) and _names_match(away_en, af_away):
                    matched_af = af
                    break

            if not matched_af:
                results.append({**f,
                    "af_league_id": lid, "af_fixture_id": None,
                    "home_matched": False, "away_matched": False,
                    "has_standings": has_standings,
                    "has_team_stats": False, "has_form": False,
                    "has_predictions": False,
                    "coverage": "no_fixture_match",
                })
                continue

            af_fix_id  = matched_af["fixture"]["id"]
            af_home_id = matched_af["teams"]["home"]["id"]

            # Team statistics (sampled once per bucket to save quota)
            stats_key = (lid, season)
            if stats_key not in teamstats_cache and not sampled_team_stats:
                try:
                    stats = get_team_statistics(lid, season, af_home_id)
                    teamstats_cache[stats_key] = stats is not None
                    sampled_team_stats = True
                except Exception:
                    teamstats_cache[stats_key] = False
                    sampled_team_stats = True

            has_team_stats = teamstats_cache.get(stats_key, False)
            has_form = has_team_stats  # form is part of team stats

            # AF predictions are reference-only; not part of coverage requirement.
            has_predictions = False

            all_data = has_standings and has_team_stats
            coverage = "full" if all_data else ("partial" if has_standings else "minimal")

            results.append({**f,
                "af_league_id":  lid,
                "af_fixture_id": af_fix_id,
                "home_matched":  True,
                "away_matched":  True,
                "has_standings": has_standings,
                "has_team_stats": has_team_stats,
                "has_form":      has_form,
                "has_predictions": has_predictions,
                "coverage":      coverage,
            })

    # ── Print coverage table ─────────────────────────────────────────────────
    def _yn(v: bool) -> str:
        return "Y" if v else "N"

    print(f"\nAPI-Football Coverage Probe — week {week}/{year}\n")
    print(
        f"  {'Coupon':<8} {'#':>2}  "
        f"{'NT Competition':<42}  "
        f"{'Home':<25} vs {'Away':<25}  "
        f"{'AF Lg':>5}  {'Mtch':>4}  "
        f"{'Stand':>5} {'Stats':>5} {'Form':>4} {'Pred':>4}  "
        f"Coverage"
    )
    print("  " + "-" * 155)

    for r in sorted(results, key=lambda x: (x["coupon"], x["num"])):
        af_lg = str(r["af_league_id"]) if r["af_league_id"] else "—"
        af_fx = str(r["af_fixture_id"]) if r["af_fixture_id"] else "—"
        mtch  = "Y" if r["home_matched"] and r["away_matched"] else "N"
        print(
            f"  {r['coupon']:<8} {r['num']:>2}  "
            f"{r['arrangement'][:42]:<42}  "
            f"{r['home'][:25]:<25} vs {r['away'][:25]:<25}  "
            f"{af_lg:>5}  {mtch:>4}  "
            f"{_yn(r['has_standings']):>5} {_yn(r['has_team_stats']):>5} "
            f"{_yn(r['has_form']):>4} {_yn(r['has_predictions']):>4}  "
            f"{r['coverage']}"
        )

    # ── Summary ──────────────────────────────────────────────────────────────
    n_total      = len(results)
    n_matched    = sum(1 for r in results if r["home_matched"])
    n_standings  = sum(1 for r in results if r["has_standings"])
    n_teamstats  = sum(1 for r in results if r["has_team_stats"])
    n_form       = sum(1 for r in results if r["has_form"])
    n_preds      = sum(1 for r in results if r["has_predictions"])
    n_full       = sum(1 for r in results if r["coverage"] == "full")
    n_partial    = sum(1 for r in results if r["coverage"] == "partial")
    n_not_cov    = sum(1 for r in results if r["coverage"] == "not_covered")
    n_no_match   = sum(1 for r in results if r["coverage"] == "no_fixture_match")
    n_no_map     = sum(1 for r in results if r["coverage"] == "league_not_mapped")

    print()
    print("  -- Summary " + "-" * 50)
    print(f"  Total NT fixtures:              {n_total}")
    print(f"  Matched in API-Football:        {n_matched}  / {n_total}")
    print(f"  With standings:                 {n_standings}  / {n_total}")
    print(f"  With team statistics + form:    {n_teamstats}  / {n_total}")
    print(f"  NOTE: AF predictions excluded from coverage (reference data only).")
    print()
    print(f"  Coverage breakdown:")
    print(f"    Full (standings + stats):      {n_full}")
    print(f"    Partial (standings only):      {n_partial}")
    print(f"    No fixture match:              {n_no_match}")
    print(f"    Not covered (league absent):   {n_not_cov}")
    print(f"    League not mapped:             {n_no_map}")
    print()

    # -- Recommendation -------------------------------------------------------
    pct = round(n_matched / n_total * 100) if n_total else 0
    print("  -- Recommendation " + "-" * 42)
    if pct >= 60:
        print(
            f"  API-Football covers {n_matched}/{n_total} ({pct}%) of NT fixtures.\n"
            f"  It is a VIABLE data source for Phase 4C model foundation.\n"
            f"  Gaps: women's WC qual and lower-tier Norwegian leagues\n"
            f"  (Norsk Tipping-ligaen) are not covered.\n"
            f"  Covered competitions provide standings + form + goals (no AF predictions)."
        )
    else:
        print(
            f"  API-Football covers only {n_matched}/{n_total} ({pct}%) of NT fixtures.\n"
            f"  Coverage is insufficient as a primary enrichment source for this week.\n"
            f"  Consider it as a secondary source for domestic + major-tournament matches."
        )
    print()


# ── Main ─────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync",
        description="TippeQpongen data sync — fetch fixtures and odds",
    )
    parser.add_argument("--week",       type=int, help="ISO week number (default: current)")
    parser.add_argument("--year",       type=int, help="Year (default: current)")
    parser.add_argument("--seed-only",  action="store_true",
                        help="Flat-file seed only — no API calls")
    parser.add_argument("--nt-only",    action="store_true",
                        help="NT fixture fetch only — skip Pinnacle odds")
    parser.add_argument("--odds-only",  action="store_true",
                        help="Pinnacle odds fetch only — fixtures must already exist")
    parser.add_argument("--status",     action="store_true",
                        help="Show DB contents for the week")
    parser.add_argument("--validate",   action="store_true",
                        help="Run 10-point data integrity checks (PASS/WARN/FAIL)")
    parser.add_argument("--review",          action="store_true",
                        help="Show teams/fixtures needing manual review")
    parser.add_argument("--results-status",  action="store_true",
                        help="Show which coupons have predictions but missing results")
    parser.add_argument("--evaluate",           action="store_true",
                        help="Evaluate all coupons where predictions + results exist")
    parser.add_argument("--odds-snapshot",      action="store_true",
                        help="Fetch latest Pinnacle odds and append a timestamped snapshot")
    parser.add_argument("--mark-closing-odds",  action="store_true",
                        help="Mark last pre-kickoff snapshot as closing odds for each fixture")
    parser.add_argument("--daily",           action="store_true",
                        help="All-in-one daily sync: NT coupons + odds + snapshots + validate")
    parser.add_argument("--refresh-coupons", action="store_true",
                        help="Force-refresh coupons from NT API, replacing stale fixture data")
    parser.add_argument("--nt-debug",        action="store_true",
                        help="Print raw NT API response (first 3000 chars)")
    parser.add_argument("--api-football-coverage", action="store_true",
                        help="Probe API-Football coverage for all active NT fixtures")
    parser.add_argument("--enrich-fixtures", action="store_true",
                        help="Match NT fixtures to API-Football and store statistical enrichment")
    parser.add_argument("--af-odds", action="store_true",
                        help="Fill missing odds from API-Football for fixtures with no existing odds")
    parser.add_argument("--estimated-priors", action="store_true",
                        help="Compute model-estimated H/U/B priors for fixtures with no bookmaker odds")
    args = parser.parse_args()

    week, year = args.week, args.year
    if week is None or year is None:
        week, year = _current_week_year()

    print(f"\nTippeQpongen sync — week {week}/{year}\n")

    if args.status:
        cmd_status(week, year)
        return

    if args.validate:
        cmd_validate(week, year)
        return

    if args.review:
        cmd_review(week, year)
        return

    if args.results_status:
        cmd_results_status()
        return

    if args.evaluate:
        cmd_evaluate()
        return

    if args.odds_snapshot:
        print("Fetching Pinnacle odds snapshot...")
        cmd_odds_snapshot(week, year)
        return

    if args.mark_closing_odds:
        print("Marking closing odds...")
        cmd_mark_closing_odds()
        return

    if args.daily:
        print("Running daily sync...")
        cmd_daily(week, year)
        return

    if args.refresh_coupons:
        print(f"Refreshing coupons from NT API...")
        cmd_refresh_coupons(week, year)
        return

    if args.nt_debug:
        print("Fetching NT API with debug output...")
        cmd_fetch_nt(week, year, debug=True)
        return

    if args.api_football_coverage:
        print("Running API-Football coverage probe...")
        cmd_api_football_coverage(week, year)
        return

    if args.enrich_fixtures:
        print("Running fixture enrichment from API-Football...")
        cmd_enrich_fixtures(week, year)
        return

    if args.af_odds:
        print("Fetching API-Football odds fallback...")
        cmd_af_odds(week, year)
        return

    if args.estimated_priors:
        print(f"Computing model-estimated priors for week {week}/{year}...\n")
        summary = cmd_estimated_priors(week, year, verbose=True)
        print()
        print(f"  -- Estimated priors summary --")
        print(f"  Total fixtures:          {summary['n_total']}")
        print(f"  Skipped (has odds):      {summary['n_skipped_has_odds']}")
        print(f"  No signals available:    {summary['n_no_signals']}")
        print(f"  Estimated priors stored: {summary['n_computed']}")
        print()
        return

    if args.seed_only:
        print("Seeding from flat file...")
        ok = cmd_seed_flat_file(week, year)
        if not ok:
            sys.exit(1)
        print("\nDone. Run `streamlit run app.py` to launch the app.\n")
        return

    if args.odds_only:
        print("Fetching Pinnacle odds...")
        cmd_fetch_odds(week, year)
        print("\nDone.\n")
        return

    if args.nt_only:
        print("Step 1/1 — Fetching fixtures from Norsk Tipping...")
        ok = cmd_fetch_nt(week, year)
        if not ok:
            print("  NT API failed. Try: python sync.py --seed-only")
            sys.exit(1)
        print("\nDone. Run `streamlit run app.py` to launch the app.\n")
        return

    # ── Full sync ────────────────────────────────────────────────────────────────
    print("Step 1/2 — Fetching fixtures from Norsk Tipping API...")
    nt_ok = cmd_fetch_nt(week, year)

    if not nt_ok:
        # Only fall back to flat file if the DB has no fixtures for this week yet
        from db.coupon import list_coupons, get_coupon_matches
        existing = list_coupons(week=week, year=year)
        has_fixtures = any(
            get_coupon_matches(c["coupon_id"]) for c in existing
        )

        if has_fixtures:
            print(f"  NT API unavailable but {len(existing)} coupon(s) already in DB — keeping existing data.")
        else:
            print("\n  NT API unavailable. Falling back to flat file...")
            flat_ok = cmd_seed_flat_file(week, year)
            if not flat_ok:
                print(
                    "\n  No fixture data available for this week.\n"
                    "  Options:\n"
                    "    1. Wait for NT to publish coupons and re-run sync\n"
                    f"   2. Create data/coupon_week{week:02d}_{year}.py manually\n"
                )
                sys.exit(1)

    print("\nStep 2/2 — Fetching Pinnacle odds...")
    cmd_fetch_odds(week, year)

    print("\nDone. Run `streamlit run app.py` to launch the app.\n")


if __name__ == "__main__":
    main()
