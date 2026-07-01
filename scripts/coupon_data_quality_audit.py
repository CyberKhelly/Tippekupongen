"""
Coupon Data Quality Audit

Classifies every fixture in a coupon by the quality of its model input data
and reports which fixtures have missing odds, missing enrichment, or unknown opponents.

Usage:
    python scripts/coupon_data_quality_audit.py
    python scripts/coupon_data_quality_audit.py --week 27 --year 2026
    python scripts/coupon_data_quality_audit.py --fix   # attempt auto-link for unresolved

Output:
    Fixture table with data_quality level and odds source.
    Summary by quality tier.
    Recommendations for missing fixtures.
"""
from __future__ import annotations
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
from datetime import datetime

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tippekupongen.db")


# Quality level descriptions + priority for fix
QUALITY_LABELS = {
    "full_model":       ("Full modell",        "OK   ", "BK odds + AF enrichment"),
    "odds_only":        ("Odds, ingen enrich",  "OK   ", "BK odds but no AF enrichment"),
    "estimated_prior":  ("Estimert prior",      "WARN ", "No BK odds; estimated_prior used as fallback"),
    "nt_expert_only":   ("NT ekspert only",     "WARN ", "No BK odds, no prior; 3/3/3 placeholder"),
    "unresolved":       ("Ulosst",              "ERROR", "No data at all; 3/3/3 placeholder"),
    "unknown_opponent": ("Ukjent motstander",   "INFO ", "TBD opponent (WC bracket); no odds possible"),
}


def get_active_coupon(conn, week: int | None, year: int | None):
    if week and year:
        rows = conn.execute(
            "SELECT coupon_id, week, year, day_type, deadline_utc FROM coupons "
            "WHERE week=? AND year=? ORDER BY deadline_utc DESC",
            (week, year),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT coupon_id, week, year, day_type, deadline_utc FROM coupons "
            "ORDER BY year DESC, week DESC, deadline_utc DESC LIMIT 5"
        ).fetchall()
    return rows


def classify_fixture(conn, fid: str, away_team_id: str | None) -> str:
    import re
    if away_team_id and re.match(r"^w\d+", (away_team_id or "").lower()):
        return "unknown_opponent"

    has_odds = conn.execute(
        "SELECT 1 FROM odds WHERE fixture_id=? LIMIT 1", (fid,)
    ).fetchone()

    if has_odds:
        has_enr = conn.execute(
            "SELECT has_api_football_data FROM fixture_stat_enrichment WHERE fixture_id=?",
            (fid,),
        ).fetchone()
        if has_enr and has_enr[0]:
            return "full_model"
        return "odds_only"

    has_prior = conn.execute(
        "SELECT 1 FROM fixture_estimated_prior WHERE fixture_id=? LIMIT 1", (fid,)
    ).fetchone()
    if has_prior:
        return "estimated_prior"

    has_expert = conn.execute(
        "SELECT expert_h FROM coupon_fixtures WHERE fixture_id=? AND expert_h IS NOT NULL LIMIT 1",
        (fid,),
    ).fetchone()
    if has_expert:
        return "nt_expert_only"

    return "unresolved"


def audit_coupon(conn, coupon_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT cf.match_number, cf.fixture_id, cf.arrangement_name,
                  cf.expert_h, cf.expert_u, cf.expert_b,
                  cf.public_h, cf.public_u, cf.public_b,
                  f.kickoff_utc, f.home_team_id, f.away_team_id,
                  COALESCE(th.name_local, th.name_canonical) AS home_name,
                  COALESCE(ta.name_local, ta.name_canonical) AS away_name,
                  o.odds_h, o.odds_u, o.odds_b, o.source AS odds_src,
                  ep.estimated_h, ep.estimated_u, ep.estimated_b,
                  lnk.api_football_fixture_id AS af_fid,
                  lnk.api_football_league_id  AS af_lid,
                  lnk.match_confidence        AS af_conf,
                  lnk.link_source,
                  lnk.af_league_name,
                  lnk.af_country
           FROM coupon_fixtures cf
           JOIN fixtures f ON f.fixture_id = cf.fixture_id
           JOIN teams th   ON th.team_id   = f.home_team_id
           JOIN teams ta   ON ta.team_id   = f.away_team_id
           LEFT JOIN odds o ON o.id = (
               SELECT id FROM odds oi WHERE oi.fixture_id = f.fixture_id
               ORDER BY CASE oi.source
                   WHEN 'pinnacle' THEN 1 WHEN 'norsk_tipping' THEN 2
                   WHEN 'manual' THEN 3 ELSE 4 END,
                   oi.fetched_at DESC LIMIT 1
           )
           LEFT JOIN fixture_estimated_prior ep ON ep.fixture_id = f.fixture_id
           LEFT JOIN api_football_fixture_links lnk ON lnk.fixture_id = f.fixture_id
           WHERE cf.coupon_id = ?
           ORDER BY cf.match_number""",
        (coupon_id,),
    ).fetchall()

    result = []
    for r in rows:
        fid     = r["fixture_id"]
        quality = classify_fixture(conn, fid, r["away_team_id"])

        # Determine effective odds (what the model actually uses)
        if r["odds_h"] is not None:
            eff_h, eff_u, eff_b = r["odds_h"], r["odds_u"], r["odds_b"]
            eff_src = r["odds_src"] or "bookmaker"
        elif r["estimated_h"] is not None:
            try:
                eff_h = round(1.0 / r["estimated_h"], 3)
                eff_u = round(1.0 / r["estimated_u"], 3)
                eff_b = round(1.0 / r["estimated_b"], 3)
                eff_src = "estimated_prior"
            except (ZeroDivisionError, TypeError):
                eff_h = eff_u = eff_b = 3.0
                eff_src = "placeholder"
        else:
            eff_h = eff_u = eff_b = 3.0
            eff_src = "placeholder"

        result.append({
            "match_number":   r["match_number"],
            "fixture_id":     fid,
            "home_name":      r["home_name"] or "?",
            "away_name":      r["away_name"] or "?",
            "arrangement":    r["arrangement_name"] or "?",
            "kickoff":        (r["kickoff_utc"] or "")[:16],
            "data_quality":   quality,
            "eff_h":          eff_h,
            "eff_u":          eff_u,
            "eff_b":          eff_b,
            "eff_src":        eff_src,
            "has_bk_odds":    r["odds_h"] is not None,
            "has_ep":         r["estimated_h"] is not None,
            "has_expert":     r["expert_h"] is not None,
            "af_fid":         r["af_fid"],
            "af_lid":         r["af_lid"],
            "af_conf":        r["af_conf"],
            "link_source":    r["link_source"],
            "af_league_name": r["af_league_name"],
            "af_country":     r["af_country"],
        })

    return result


def print_report(coupon_id: str, rows: list[dict]) -> None:
    SEP = "=" * 110

    print(SEP)
    print(f"COUPON DATA QUALITY REPORT — {coupon_id}")
    print(SEP)

    hdr = f"{'#':>2}  {'HOME':20s}  {'AWAY':20s}  {'ARRANGEMENT':22s}  {'STATUS':6s}  {'QUALITY':19s}  {'EFF H/U/B':20s}  {'SRC':18s}"
    print(hdr)
    print("-" * 110)

    quality_counts: dict[str, int] = {}
    for r in rows:
        q = r["data_quality"]
        quality_counts[q] = quality_counts.get(q, 0) + 1
        label, status, _ = QUALITY_LABELS.get(q, (q, "???", ""))
        odds_str = f"{r['eff_h']:.2f}/{r['eff_u']:.2f}/{r['eff_b']:.2f}" if r["eff_h"] else "—"
        print(
            f"{r['match_number']:>2}  {r['home_name'][:20]:20s}  {r['away_name'][:20]:20s}  "
            f"{r['arrangement'][:22]:22s}  {status}  {label[:19]:19s}  "
            f"{odds_str:20s}  {r['eff_src'][:18]:18s}"
        )

    print()
    print("SUMMARY")
    print("-" * 60)
    for q, cnt in sorted(quality_counts.items(), key=lambda x: list(QUALITY_LABELS).index(x[0]) if x[0] in QUALITY_LABELS else 99):
        label, status, desc = QUALITY_LABELS.get(q, (q, "???", q))
        print(f"  {status}  {label:20s}  {cnt:2d}  — {desc}")

    print()
    print("DETAIL — non-full-model fixtures")
    print("-" * 110)
    for r in rows:
        q = r["data_quality"]
        if q == "full_model":
            continue
        label, status, desc = QUALITY_LABELS.get(q, (q, "???", q))
        print(f"  Match #{r['match_number']}: {r['home_name']} vs {r['away_name']}")
        print(f"    data_quality : {label} ({status})")
        print(f"    arrangement  : {r['arrangement']}")
        print(f"    AF link      : {'af_id=' + str(r['af_fid']) + '  league=' + str(r['af_lid']) + '  src=' + str(r['link_source']) if r['af_fid'] else 'NONE'}")
        if r["af_league_name"]:
            print(f"    AF league    : {r['af_league_name']} ({r['af_country']})")
        print(f"    Has BK odds  : {'YES' if r['has_bk_odds'] else 'NO'}")
        print(f"    Has est.prior: {'YES' if r['has_ep'] else 'NO'}")
        print(f"    Has NT expert: {'YES' if r['has_expert'] else 'NO'}")
        print(f"    Effective odds (model sees): {r['eff_h']}/{r['eff_u']}/{r['eff_b']} ({r['eff_src']})")
        print()

    # Fixability table for non-full fixtures
    needs_fix = [r for r in rows if r["data_quality"] not in ("full_model", "unknown_opponent")]
    if needs_fix:
        print("FIXABILITY")
        print("-" * 90)
        for r in needs_fix:
            q = r["data_quality"]
            if q == "odds_only":
                fix = "Run sync.py --daily to trigger enrichment"
            elif q == "estimated_prior":
                fix = "Odds scanner may cover this league — check _SCAN_LEAGUES"
            elif q == "nt_expert_only":
                fix = "Run auto_link_unresolved_coupon_fixtures() then enrich"
            else:
                fix = "Run auto_link_unresolved_coupon_fixtures() then check"
            print(f"  Match #{r['match_number']:>2}  {r['home_name'][:18]:18s} vs {r['away_name'][:18]:18s}  -> {fix}")


def main():
    parser = argparse.ArgumentParser(description="Coupon data quality audit")
    parser.add_argument("--week", type=int, help="NT coupon week")
    parser.add_argument("--year", type=int, help="NT coupon year")
    parser.add_argument("--coupon", type=str, help="Specific coupon_id")
    parser.add_argument("--fix",   action="store_true", help="Attempt auto-link for unresolved fixtures")
    args = parser.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    if args.coupon:
        coupon_ids = [args.coupon]
        print(f"Auditing coupon: {args.coupon}")
    else:
        coupon_rows = get_active_coupon(conn, args.week, args.year)
        if not coupon_rows:
            print("No coupons found.")
            conn.close()
            sys.exit(1)
        coupon_ids = [r["coupon_id"] for r in coupon_rows]
        print(f"Found {len(coupon_ids)} coupon(s): {', '.join(coupon_ids)}")
        print()

    all_rows: list[dict] = []
    for cid in coupon_ids:
        rows = audit_coupon(conn, cid)
        all_rows.extend(rows)
        print_report(cid, rows)
        print()

    conn.close()

    if args.fix:
        # Determine week/year from args or from the coupon
        if args.week and args.year:
            w, y = args.week, args.year
        else:
            # Parse from coupon_id if possible
            parts = coupon_ids[0].rsplit("-", 2)
            try:
                w, y = int(parts[-2]), int(parts[-1])
            except (ValueError, IndexError):
                print("Cannot determine week/year from coupon_id — pass --week and --year")
                sys.exit(1)

        print(f"Running auto-link fallback for week {w}/{y}...")
        from ingestion.enrich_fixtures import auto_link_unresolved_coupon_fixtures
        result = auto_link_unresolved_coupon_fixtures(w, y, verbose=True)
        print()
        print("Auto-link result:")
        for k, v in result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
