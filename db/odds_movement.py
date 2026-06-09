"""
Odds movement and Closing Line Value (CLV) tracking.

odds_snapshots stores every odds fetch timestamped, enabling:
  - opening / latest / closing odds per fixture
  - CLV: how well the coupon odds beat the closing line

CLV formula:  clv = (prediction_odds / closing_odds) - 1
  Positive CLV → you got better odds than what the market closed at (good).
  Negative CLV → the market moved away from you (bad).

Closing odds: the last snapshot fetched before kickoff_utc.
Mark them explicitly with --mark-closing-odds after the match starts.
"""
import uuid
from datetime import datetime, timezone
from db.connection import get_conn


# ── Implied probability ──────────────────────────────────────────────────────────

def _devig(odds_h: float, odds_u: float, odds_b: float) -> tuple[float, float, float]:
    """Remove bookmaker margin; return normalized probabilities (sum = 1)."""
    raw_h = 1.0 / odds_h
    raw_u = 1.0 / odds_u
    raw_b = 1.0 / odds_b
    total = raw_h + raw_u + raw_b
    return round(raw_h / total, 6), round(raw_u / total, 6), round(raw_b / total, 6)


# ── Snapshots ────────────────────────────────────────────────────────────────────

def save_snapshot(
    fixture_id: str,
    bookmaker: str,
    market: str,
    odds_h: float,
    odds_u: float,
    odds_b: float,
    source: str,
    fetched_at: str | None = None,
) -> str | None:
    """
    Append a timestamped odds snapshot. Silently ignores duplicates
    (same fixture/bookmaker/market/fetched_at — can happen if fetch runs twice
    in the same second).
    Returns snapshot_id or None if duplicate.
    """
    prob_h, prob_u, prob_b = _devig(odds_h, odds_u, odds_b)
    now = fetched_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    snap_id = str(uuid.uuid4())
    with get_conn() as conn:
        try:
            conn.execute(
                """INSERT INTO odds_snapshots
                   (snapshot_id, fixture_id, bookmaker, market,
                    odds_h, odds_u, odds_b,
                    implied_prob_h, implied_prob_u, implied_prob_b,
                    fetched_at, source, is_closing_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (snap_id, fixture_id, bookmaker, market,
                 odds_h, odds_u, odds_b,
                 prob_h, prob_u, prob_b,
                 now, source),
            )
        except Exception:
            return None  # duplicate — silently skip
    return snap_id


def get_snapshots_for_fixture(
    fixture_id: str,
    bookmaker: str = "pinnacle",
    market: str = "h2h",
) -> list[dict]:
    """Return all snapshots for a fixture ordered oldest→newest."""
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE fixture_id=? AND bookmaker=? AND market=?
               ORDER BY fetched_at ASC""",
            (fixture_id, bookmaker, market),
        ).fetchall()
    return [dict(r) for r in rows]


def get_opening_snapshot(
    fixture_id: str, bookmaker: str = "pinnacle", market: str = "h2h"
) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE fixture_id=? AND bookmaker=? AND market=?
               ORDER BY fetched_at ASC LIMIT 1""",
            (fixture_id, bookmaker, market),
        ).fetchone()
    return dict(row) if row else None


def get_latest_snapshot(
    fixture_id: str, bookmaker: str = "pinnacle", market: str = "h2h"
) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE fixture_id=? AND bookmaker=? AND market=?
               ORDER BY fetched_at DESC LIMIT 1""",
            (fixture_id, bookmaker, market),
        ).fetchone()
    return dict(row) if row else None


def get_closing_snapshot(
    fixture_id: str, bookmaker: str = "pinnacle", market: str = "h2h"
) -> dict | None:
    """Return the explicitly marked closing snapshot, or None."""
    with get_conn() as conn:
        row = conn.execute(
            """SELECT * FROM odds_snapshots
               WHERE fixture_id=? AND bookmaker=? AND market=?
                 AND is_closing_snapshot=1
               ORDER BY fetched_at DESC LIMIT 1""",
            (fixture_id, bookmaker, market),
        ).fetchone()
    return dict(row) if row else None


# ── Closing odds marking ──────────────────────────────────────────────────────────

def mark_closing_for_fixture(
    fixture_id: str,
    bookmaker: str = "pinnacle",
    market: str = "h2h",
) -> bool:
    """
    Mark the last snapshot fetched before kickoff_utc as the closing snapshot.
    Clears is_closing_snapshot on all other rows for this fixture/bookmaker/market.
    Returns True if a closing snapshot was found and marked.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT kickoff_utc FROM fixtures WHERE fixture_id=?", (fixture_id,)
        ).fetchone()
        if not row:
            return False
        kickoff = row["kickoff_utc"]

        # Find the last snapshot before kickoff
        closing = conn.execute(
            """SELECT snapshot_id FROM odds_snapshots
               WHERE fixture_id=? AND bookmaker=? AND market=?
                 AND fetched_at < ?
               ORDER BY fetched_at DESC LIMIT 1""",
            (fixture_id, bookmaker, market, kickoff),
        ).fetchone()

        if not closing:
            return False

        closing_id = closing["snapshot_id"]
        # Reset all closing flags for this fixture/bookmaker/market
        conn.execute(
            """UPDATE odds_snapshots SET is_closing_snapshot=0
               WHERE fixture_id=? AND bookmaker=? AND market=?""",
            (fixture_id, bookmaker, market),
        )
        # Mark the chosen one
        conn.execute(
            "UPDATE odds_snapshots SET is_closing_snapshot=1 WHERE snapshot_id=?",
            (closing_id,),
        )
    return True


def mark_all_closing(bookmaker: str = "pinnacle", market: str = "h2h") -> int:
    """
    Run mark_closing_for_fixture for every fixture that has snapshots.
    Returns number of fixtures where a closing snapshot was marked.
    """
    with get_conn() as conn:
        fixture_ids = [
            r[0] for r in conn.execute(
                "SELECT DISTINCT fixture_id FROM odds_snapshots WHERE bookmaker=? AND market=?",
                (bookmaker, market),
            ).fetchall()
        ]
    count = 0
    for fid in fixture_ids:
        if mark_closing_for_fixture(fid, bookmaker, market):
            count += 1
    return count


# ── CLV calculation ───────────────────────────────────────────────────────────────

def compute_clv(prediction_odds: float, closing_odds: float) -> float:
    """
    CLV = (prediction_odds / closing_odds) - 1

    Positive: you got better odds than the market closed at.
    Negative: the market moved against your pick.
    """
    if not closing_odds or closing_odds <= 0:
        return 0.0
    return round((prediction_odds / closing_odds) - 1, 4)


def get_clv_for_coupon(
    coupon_id: str, bookmaker: str = "pinnacle", market: str = "h2h"
) -> list[dict]:
    """
    For each prediction in a coupon, compute CLV using the closing snapshot.

    Returns list of dicts with keys:
      fixture_id, match_number, home_name, away_name,
      recommended_pick, selected_outcomes,
      pred_odds_h, pred_odds_u, pred_odds_b,
      closing_odds_h, closing_odds_u, closing_odds_b,
      clv_h, clv_u, clv_b, clv_selected
    """
    with get_conn() as conn:
        preds = conn.execute(
            """SELECT p.fixture_id, p.match_number, p.recommended_pick,
                      p.selected_outcomes, p.odds_h, p.odds_u, p.odds_b,
                      COALESCE(th.name_local, th.name_canonical) AS home_name,
                      COALESCE(ta.name_local, ta.name_canonical) AS away_name
               FROM coupon_predictions p
               JOIN fixtures f ON f.fixture_id = p.fixture_id
               JOIN teams th   ON th.team_id   = f.home_team_id
               JOIN teams ta   ON ta.team_id   = f.away_team_id
               WHERE p.coupon_id=?
               ORDER BY p.match_number""",
            (coupon_id,),
        ).fetchall()

    import json
    result = []
    for p in preds:
        pd = dict(p)
        closing = get_closing_snapshot(pd["fixture_id"], bookmaker, market)

        co_h = closing["odds_h"] if closing else None
        co_u = closing["odds_u"] if closing else None
        co_b = closing["odds_b"] if closing else None

        clv_h = compute_clv(pd["odds_h"], co_h) if pd["odds_h"] and co_h else None
        clv_u = compute_clv(pd["odds_u"], co_u) if pd["odds_u"] and co_u else None
        clv_b = compute_clv(pd["odds_b"], co_b) if pd["odds_b"] and co_b else None

        pick = pd["recommended_pick"]
        clv_sel = {"H": clv_h, "U": clv_u, "B": clv_b}.get(pick)

        try:
            sel_out = json.loads(pd["selected_outcomes"])
        except Exception:
            sel_out = []

        result.append({
            "fixture_id":       pd["fixture_id"],
            "match_number":     pd["match_number"],
            "home_name":        pd["home_name"],
            "away_name":        pd["away_name"],
            "recommended_pick": pd["recommended_pick"],
            "selected_outcomes":sel_out,
            "pred_odds_h":      pd["odds_h"],
            "pred_odds_u":      pd["odds_u"],
            "pred_odds_b":      pd["odds_b"],
            "closing_odds_h":   co_h,
            "closing_odds_u":   co_u,
            "closing_odds_b":   co_b,
            "clv_h":            clv_h,
            "clv_u":            clv_u,
            "clv_b":            clv_b,
            "clv_selected":     clv_sel,
        })

    return result


def get_snapshot_summary_for_coupon(
    coupon_id: str, bookmaker: str = "pinnacle", market: str = "h2h"
) -> list[dict]:
    """
    For each fixture in a coupon, return opening/latest/closing snapshot summary.
    """
    with get_conn() as conn:
        fixture_ids = [
            r[0] for r in conn.execute(
                """SELECT DISTINCT p.fixture_id
                   FROM coupon_predictions p WHERE p.coupon_id=?""",
                (coupon_id,),
            ).fetchall()
        ]

    summaries = []
    for fid in fixture_ids:
        opening = get_opening_snapshot(fid, bookmaker, market)
        latest  = get_latest_snapshot(fid, bookmaker, market)
        closing = get_closing_snapshot(fid, bookmaker, market)
        summaries.append({
            "fixture_id": fid,
            "opening":    opening,
            "latest":     latest,
            "closing":    closing,
            "n_snapshots": len(get_snapshots_for_fixture(fid, bookmaker, market)),
        })
    return summaries
