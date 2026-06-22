"""
Shared pipeline for the FastAPI backend.

build_matches() mirrors the load_matches() logic in app.py exactly:
    process_match → run_model → classify_match

Both Streamlit (app.py) and FastAPI (backend/main.py) call the same underlying
analysis functions. This module holds no new logic — it is just a clean entry
point that takes an explicit coupon_id instead of Streamlit session state.
"""
from __future__ import annotations

from datetime import datetime

from analysis.classifier import classify_match
from analysis.model import run_model
from analysis.probability import process_match
from data.loader import load_coupons
from models.match import Match


def parse_coupon_id(coupon_id: str) -> tuple[str, int, int]:
    """
    Parse a coupon_id like 'midtuke-25-2026' into (key, week, year).
    Falls back to current ISO week if the format is unexpected.
    """
    parts = coupon_id.rsplit("-", 2)
    if len(parts) == 3:
        try:
            return parts[0], int(parts[1]), int(parts[2])
        except ValueError:
            pass
    iso = datetime.now().isocalendar()
    return coupon_id, iso.week, iso.year


def build_matches(coupon_id: str) -> list[Match]:
    """
    Build a fully-processed list of Match objects for the given coupon_id.

    Pipeline per fixture:
        1. Load odds/team data from DB (or flat-file fallback via load_coupons)
        2. Load AF enrichment from DB if available
        3. process_match()  — odds → normalised probabilities
        4. run_model()      — bookmaker prior + stats adjustment + crowd signals
        5. classify_match() — banker / uncertain / half_cover / full_cover / standard

    Raises KeyError when coupon_id is not found.
    """
    coupon_key, week, year = parse_coupon_id(coupon_id)

    # Load AF enrichment (optional — silently skipped if unavailable)
    enrichment_map: dict[int, dict] = {}
    try:
        from db.enrichment import get_coupon_enrichment
        from db.schema import init_db
        init_db()
        for row in get_coupon_enrichment(coupon_id):
            enrichment_map[row["match_number"]] = row
    except Exception:
        pass

    coupons = load_coupons(week=week, year=year)
    if coupon_key not in coupons:
        raise KeyError(f"Coupon key '{coupon_key}' not found for week {week}/{year}")

    matches: list[Match] = []
    for i, row in enumerate(coupons[coupon_key]["matches"], 1):
        home, away, oh, ou, ob = row[:5]
        src = row[5] if len(row) > 5 else ""
        m = Match(
            number=i,
            home_team=home,
            away_team=away,
            odds_h=oh,
            odds_u=ou,
            odds_b=ob,
            odds_source=src,
        )
        if i in enrichment_map:
            m.fixture_id = enrichment_map[i].get("fixture_id")
        process_match(m)
        enr = enrichment_map.get(i)
        if m.odds_source == "placeholder" and enr:
            ep_h = enr.get("estimated_h")
            ep_u = enr.get("estimated_u")
            ep_b = enr.get("estimated_b")
            if ep_h is not None and ep_u is not None and ep_b is not None:
                total = float(ep_h) + float(ep_u) + float(ep_b)
                if total > 0:
                    m.prob_h = float(ep_h) / total
                    m.prob_u = float(ep_u) / total
                    m.prob_b = float(ep_b) / total
                    m.odds_source = "estimated_prior"
        run_model(m, enr)
        classify_match(m)
        matches.append(m)

    return matches
