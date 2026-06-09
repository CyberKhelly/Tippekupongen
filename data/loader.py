"""
Unified coupon loader.

Priority:
  1. SQLite database — most recent odds, API-sourced fixtures
  2. Flat-file data module matching the current ISO week
  3. Latest flat-file data module (hard fallback)

The returned dict is drop-in compatible with the existing COUPONS format:
    {
        "midtuke": {"label": str, "deadline": str, "matches": [...]},
        "lordag":  {"label": str, "deadline": str, "matches": [...]},
        "sondag":  {"label": str, "deadline": str, "matches": [...]},
    }
"""
from __future__ import annotations
import importlib
from datetime import datetime


def _current_week_year() -> tuple[int, int]:
    iso = datetime.now().isocalendar()
    return iso.week, iso.year


def _best_odds(r: dict) -> tuple[float, float, float, str]:
    """
    Return (odds_h, odds_u, odds_b, source) for a match row.

    Priority:
      1. Bookmaker odds from the odds table (pinnacle, betsson, etc.)
      2. NT expert tip percentages as synthetic decimal odds (100 / pct)
         — expert tips track Pinnacle within ~2–5% on verified fixtures.
      3. Equal-probability placeholder 3.0/3.0/3.0 as last resort.

    The synthetic-odds approach feeds expert tip percentages through the
    existing process_match() pipeline unchanged: since the tips already
    sum to ~100%, 1/synthetic_odds reproduces the original percentages
    after process_match()'s normalization step.
    """
    if r.get("odds_h") is not None:
        src = r.get("source") or "bookmaker"
        return float(r["odds_h"]), float(r["odds_u"]), float(r["odds_b"]), src

    eh = r.get("expert_h")
    eu = r.get("expert_u")
    eb = r.get("expert_b")
    if eh and eu and eb and float(eh) > 0 and float(eu) > 0 and float(eb) > 0:
        return (
            round(100.0 / float(eh), 4),
            round(100.0 / float(eu), 4),
            round(100.0 / float(eb), 4),
            "nt_expert",
        )

    return 3.0, 3.0, 3.0, "placeholder"


def _load_from_db(week: int, year: int) -> dict | None:
    """Return COUPONS-shaped dict from SQLite, or None if unavailable."""
    try:
        from db.coupon import list_coupons, get_coupon_matches
        coupons = list_coupons(week=week, year=year)
    except Exception:
        return None

    if not coupons:
        return None

    result: dict = {}
    for coupon in coupons:
        coupon_id = coupon["coupon_id"]
        # coupon_id format: "{key}-{week:02d}-{year}"
        key = coupon_id[: -(len(f"-{week:02d}-{year}"))]

        try:
            rows = get_coupon_matches(coupon_id)
        except Exception:
            continue

        matches = []
        for r in rows:
            oh, ou, ob, src = _best_odds(r)
            matches.append((r["home_name"], r["away_name"], oh, ou, ob, src))

        if matches:
            result[key] = {
                "label":    coupon["label"],
                "deadline": coupon["deadline_utc"],
                "matches":  matches,
            }

    return result or None


def _load_flat_file(week: int, year: int) -> dict | None:
    """Try to import data/coupon_weekNN_YYYY.py for the given week."""
    module_name = f"data.coupon_week{week:02d}_{year}"
    try:
        module = importlib.import_module(module_name)
        return module.COUPONS
    except ModuleNotFoundError:
        return None


def load_coupons(week: int | None = None, year: int | None = None) -> dict:
    """
    Return a COUPONS dict for the given week/year.
    Falls back through DB → flat file → hard-coded fallback.
    """
    if week is None or year is None:
        week, year = _current_week_year()

    data = _load_from_db(week, year)
    if data:
        return data

    data = _load_flat_file(week, year)
    if data:
        return data

    # Last resort: find and load the most recent available flat-file module.
    import glob, os
    flat_dir = os.path.dirname(__file__)
    candidates = sorted(glob.glob(os.path.join(flat_dir, "coupon_week??_????.py")))
    for path in reversed(candidates):
        module_name = "data." + os.path.basename(path)[:-3]
        try:
            module = importlib.import_module(module_name)
            return module.COUPONS
        except Exception:
            continue

    return {}
