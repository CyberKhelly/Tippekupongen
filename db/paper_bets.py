"""
Paper bet (Modellspill) tracking.

Bets are generated from model edge signals against bookmaker implied probability.
No NT public percentages are used — betting edge is purely model vs market.
No real money is involved.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from db.connection import get_conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Stake sizing ───────────────────────────────────────────────────────────────

def tier_stake(edge_pp: float, model_prob: float, insight_type: str) -> float:
    """
    Simple tiered staking based on model edge and confidence.
    Longshots are capped at 200 NOK regardless of edge.
    """
    if model_prob < 0.30 or insight_type == "longshot":
        return 200 if edge_pp >= 8 else 100
    if edge_pp >= 12 and model_prob >= 0.55:
        return 1000
    if edge_pp >= 8:
        return 500
    if edge_pp >= 5:
        return 200
    return 100


def get_risk_level(edge_pp: float, model_prob: float) -> str:
    if model_prob < 0.30 or edge_pp < 5:
        return "high"
    if model_prob >= 0.55 and edge_pp >= 8:
        return "low"
    return "medium"


# ── Write ──────────────────────────────────────────────────────────────────────

# Quality ranking for contradictory-bet resolution (higher = better)
_QUALITY_RANK: dict[str, int] = {"full_model": 3, "af_supported": 2, "generic_prior": 1}


def create_bet(
    *,
    fixture_id: str,
    match_name: str,
    market: str,
    outcome: str,
    bookmaker: str,
    ref_odds: float,
    implied_prob: float,   # fraction 0-1
    model_prob: float,     # fraction 0-1
    edge_pp: float,        # (model_prob - implied_prob) * 100
    insight_type: str | None = None,
    reason: str | None = None,
    league: str | None = None,
    kickoff_utc: str | None = None,
    coupon_id: str | None = None,
    model_quality: str | None = None,
    debug_json: str | None = None,
) -> str:
    risk_level = get_risk_level(edge_pp, model_prob)
    stake = tier_stake(edge_pp, model_prob, insight_type or "")
    ev = round(model_prob * ref_odds - 1, 4)
    bet_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO model_bets
               (id, coupon_id, fixture_id, match_name, league, kickoff_utc,
                market, outcome, bookmaker, ref_odds, implied_prob, model_prob,
                edge_pp, stake_nok, expected_value, insight_type, risk_level,
                reason, model_quality, debug_json, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (bet_id, coupon_id, fixture_id, match_name, league, kickoff_utc,
             market, outcome, bookmaker, ref_odds, implied_prob, model_prob,
             edge_pp, stake, ev, insight_type, risk_level, reason, model_quality,
             debug_json, _now()),
        )
    return bet_id


def bet_exists(fixture_id: str, market: str, outcome: str, coupon_id: str | None = None) -> bool:
    """Prevent duplicate bets for the same fixture/market/outcome within a coupon."""
    with get_conn() as conn:
        if coupon_id:
            row = conn.execute(
                """SELECT 1 FROM model_bets
                   WHERE fixture_id=? AND market=? AND outcome=? AND coupon_id=?
                     AND status != 'void'""",
                (fixture_id, market, outcome, coupon_id),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT 1 FROM model_bets
                   WHERE fixture_id=? AND market=? AND outcome=? AND status != 'void'""",
                (fixture_id, market, outcome),
            ).fetchone()
    return row is not None


def get_conflicting_bet(fixture_id: str, market: str, outcome: str) -> dict | None:
    """
    Return a pending bet that would conflict with the proposed bet.
    - btts: yes <-> no
    - over_2.5: over <-> under
    - 1x2: any other pending outcome on the same fixture+market
    Returns None if no conflict found.
    """
    with get_conn() as conn:
        if market == "1x2":
            row = conn.execute(
                """SELECT id, model_quality, edge_pp, expected_value FROM model_bets
                   WHERE fixture_id=? AND market=? AND outcome != ? AND status='pending'
                   ORDER BY edge_pp DESC LIMIT 1""",
                (fixture_id, market, outcome),
            ).fetchone()
        elif market == "btts":
            opposite = "no" if outcome == "yes" else "yes"
            row = conn.execute(
                """SELECT id, model_quality, edge_pp, expected_value FROM model_bets
                   WHERE fixture_id=? AND market=? AND outcome=? AND status='pending'""",
                (fixture_id, market, opposite),
            ).fetchone()
        elif market == "over_2.5":
            opposite = "under" if outcome == "over" else "over"
            row = conn.execute(
                """SELECT id, model_quality, edge_pp, expected_value FROM model_bets
                   WHERE fixture_id=? AND market=? AND outcome=? AND status='pending'""",
                (fixture_id, market, opposite),
            ).fetchone()
        else:
            return None
    return dict(row) if row else None


def void_bet(bet_id: str) -> None:
    """Void a pending bet (superseded by a higher-quality conflicting bet)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE model_bets SET status='void' WHERE id=? AND status='pending'",
            (bet_id,),
        )


def delete_all_model_bets() -> int:
    """
    Hard-delete every row in model_bets — all statuses.
    Used to reset the Modellspill ledger before a clean launch.
    Returns the number of rows deleted.
    """
    with get_conn() as conn:
        n = conn.execute("DELETE FROM model_bets").rowcount
    return n


def resolve_contradictory_bets() -> int:
    """
    Void the weaker bet in each contradictory pending pair.
    Contradictory = same fixture+market but different outcomes.
    Quality ordering: full_model > af_supported > generic_prior.
    Tiebreaker: higher edge_pp wins.
    Returns number of bets voided.
    """
    voided = 0
    with get_conn() as conn:
        pairs = conn.execute("""
            SELECT a.id AS a_id, a.model_quality AS a_mq, a.edge_pp AS a_ep,
                   b.id AS b_id, b.model_quality AS b_mq, b.edge_pp AS b_ep
            FROM model_bets a
            JOIN model_bets b
              ON a.fixture_id = b.fixture_id
             AND a.market = b.market
             AND a.outcome != b.outcome
             AND a.id < b.id
            WHERE a.status = 'pending' AND b.status = 'pending'
        """).fetchall()

        for p in pairs:
            a_rank = _QUALITY_RANK.get(p["a_mq"] or "", 0)
            b_rank = _QUALITY_RANK.get(p["b_mq"] or "", 0)
            a_ep   = p["a_ep"] or 0.0
            b_ep   = p["b_ep"] or 0.0
            if a_rank > b_rank or (a_rank == b_rank and a_ep >= b_ep):
                conn.execute("UPDATE model_bets SET status='void' WHERE id=?", (p["b_id"],))
            else:
                conn.execute("UPDATE model_bets SET status='void' WHERE id=?", (p["a_id"],))
            voided += 1
    return voided


# ── Read ───────────────────────────────────────────────────────────────────────

def list_bets(
    status: str | None = None,
    market: str | None = None,
    limit: int = 200,
) -> list[dict]:
    parts: list[str] = []
    params: list = []
    if status:
        parts.append("status = ?")
        params.append(status)
    if market:
        parts.append("market = ?")
        params.append(market)
    where = f"WHERE {' AND '.join(parts)}" if parts else ""
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM model_bets {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


# ── Settlement ────────────────────────────────────────────────────────────────

def settle_pending_bets(fixture_id: str) -> int:
    """
    Settle all pending model_bets for a fixture using match_results.
    Returns number of bets settled.

    Markets:
      1x2       — outcome must match result_1x2 (H/U/B)
      btts      — 'yes' if both teams scored, 'no' otherwise
      over_2.5  — 'over' if total goals > 2.5, 'under' otherwise
    """
    with get_conn() as conn:
        result_row = conn.execute(
            "SELECT result_1x2, home_score, away_score FROM match_results WHERE fixture_id=?",
            (fixture_id,),
        ).fetchone()
        if not result_row:
            return 0

        r1x2      = result_row["result_1x2"]
        home_g    = result_row["home_score"] or 0
        away_g    = result_row["away_score"] or 0
        total_g   = home_g + away_g
        btts_res  = "yes" if (home_g > 0 and away_g > 0) else "no"
        ou_res    = "over" if total_g > 2.5 else "under"

        pending = conn.execute(
            "SELECT * FROM model_bets WHERE fixture_id=? AND status='pending'",
            (fixture_id,),
        ).fetchall()

        now = _now()
        n_settled = 0
        for bet in pending:
            market  = bet["market"]
            outcome = bet["outcome"]

            if market == "1x2":
                won = outcome == r1x2
                actual = r1x2
            elif market == "btts":
                won = outcome == btts_res
                actual = btts_res
            elif market == "over_2.5":
                won = outcome == ou_res
                actual = ou_res
            else:
                continue

            profit = round((bet["ref_odds"] - 1) * bet["stake_nok"], 2) if won else -bet["stake_nok"]

            conn.execute(
                """UPDATE model_bets
                   SET status=?, result_outcome=?, profit_nok=?, settled_at=?
                   WHERE id=?""",
                ("won" if won else "lost", actual, profit, now, bet["id"]),
            )
            n_settled += 1

    return n_settled


def _fetch_af_result_for_bet(fixture_id: str, af_fixture_id: int) -> tuple[int, int] | None:
    """
    Fetch final 90-minute score from API-Football.
    Accepts FT, AET, PEN statuses (all indicate the match is fully finished).
    Returns (home_score, away_score) using score.fulltime (90-min result).
    """
    try:
        from ingestion.api_football import get_fixtures
        results = get_fixtures(fixture_id=af_fixture_id)
        if not results:
            return None
        fix = results[0]
        short = fix.get("fixture", {}).get("status", {}).get("short", "")
        if short not in ("FT", "AET", "PEN"):
            return None
        # Use fulltime score (90 min) — consistent with standard bookmaker settlement
        score = fix.get("score", {})
        ft = score.get("fulltime", {})
        home_g = ft.get("home")
        away_g = ft.get("away")
        if home_g is None or away_g is None:
            # Fall back to goals field if fulltime breakdown unavailable
            goals = fix.get("goals", {})
            home_g = goals.get("home")
            away_g = goals.get("away")
        if home_g is None or away_g is None:
            return None
        return int(home_g), int(away_g)
    except Exception:
        return None


def fetch_and_settle_all_expired(buffer_minutes: int = 100) -> dict:
    """
    Fetch results from API-Football for all expired pending bets, then settle.

    - Only processes fixtures where kickoff_utc + buffer_minutes < now
    - Skips fixtures that already have a result in match_results
    - Stores results via db.history.save_result (upsert, idempotent)
    - Returns a summary dict with counts

    Safe to call repeatedly (idempotent).
    """
    from datetime import datetime, timezone, timedelta
    from db.history import save_result

    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=buffer_minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    with get_conn() as conn:
        # Find pending-bet fixtures that are past the buffer window and have an AF link
        rows = conn.execute(
            """SELECT DISTINCT mb.fixture_id, mb.kickoff_utc,
                      lnk.api_football_fixture_id
               FROM model_bets mb
               JOIN api_football_fixture_links lnk ON lnk.fixture_id = mb.fixture_id
               LEFT JOIN match_results mr ON mr.fixture_id = mb.fixture_id
               WHERE mb.status = 'pending'
                 AND mb.kickoff_utc < ?
                 AND mr.fixture_id IS NULL""",
            (cutoff,),
        ).fetchall()

    results_fetched = 0
    settled = 0
    won = 0
    lost = 0
    profit = 0.0
    fetch_errors = 0

    for row in rows:
        fid   = row["fixture_id"]
        af_id = row["api_football_fixture_id"]

        score = _fetch_af_result_for_bet(fid, af_id)
        if score is None:
            fetch_errors += 1
            continue

        save_result(fid, score[0], score[1], source="api_football")
        results_fetched += 1

    # Now settle all fixtures that have results (covers both newly fetched and pre-existing)
    with get_conn() as conn:
        settle_rows = conn.execute(
            """SELECT DISTINCT mb.fixture_id FROM model_bets mb
               JOIN match_results mr ON mr.fixture_id = mb.fixture_id
               WHERE mb.status = 'pending' AND mb.kickoff_utc < ?""",
            (cutoff,),
        ).fetchall()

    for row in settle_rows:
        n = settle_pending_bets(row["fixture_id"])
        settled += n

    # Tally results from the settled bets
    with get_conn() as conn:
        tally = conn.execute(
            """SELECT status, SUM(profit_nok) as total_profit, COUNT(*) as cnt
               FROM model_bets
               WHERE settled_at >= ?
               GROUP BY status""",
            (cutoff,),
        ).fetchall()
        for t in tally:
            if t["status"] == "won":
                won = t["cnt"]
                profit += t["total_profit"] or 0
            elif t["status"] == "lost":
                lost = t["cnt"]
                profit += t["total_profit"] or 0

    return {
        "checked":         len(rows),
        "results_fetched": results_fetched,
        "fetch_errors":    fetch_errors,
        "settled":         settled,
        "won":             won,
        "lost":            lost,
        "void":            settled - won - lost,
        "profit_nok":      round(profit, 2),
    }


def update_closing_odds(fixture_id: str) -> None:
    """
    For all settled or still-pending bets on a fixture, pull the Pinnacle
    closing snapshot and store it + CLV.
    """
    from db.odds_movement import get_closing_snapshot, compute_clv
    snap = get_closing_snapshot(fixture_id)
    if not snap:
        return
    closing = {
        "H": snap["odds_h"],
        "U": snap["odds_u"],
        "B": snap["odds_b"],
    }
    with get_conn() as conn:
        bets = conn.execute(
            "SELECT id, outcome, ref_odds FROM model_bets WHERE fixture_id=? AND market='1x2' AND closing_odds IS NULL",
            (fixture_id,),
        ).fetchall()
        for bet in bets:
            co = closing.get(bet["outcome"])
            if co:
                clv = compute_clv(bet["ref_odds"], co)
                conn.execute(
                    "UPDATE model_bets SET closing_odds=?, clv=? WHERE id=?",
                    (co, clv, bet["id"]),
                )


# ── Analytics ─────────────────────────────────────────────────────────────────

def get_bankroll_history(starting_bankroll: float = 10_000.0) -> list[dict]:
    """Chronological P&L series for bankroll chart."""
    with get_conn() as conn:
        bets = conn.execute(
            """SELECT id, match_name, league, market, outcome, ref_odds,
                      stake_nok, profit_nok, settled_at
               FROM model_bets WHERE status IN ('won','lost')
               ORDER BY settled_at ASC""",
        ).fetchall()

    bankroll = starting_bankroll
    history: list[dict] = [{"bet_index": 0, "bankroll_after": bankroll, "label": "Start",
                              "profit_nok": 0.0, "market": None}]
    for i, b in enumerate(bets, 1):
        bankroll = round(bankroll + (b["profit_nok"] or 0), 2)
        history.append({
            "bet_index":      i,
            "bankroll_after": bankroll,
            "label":          b["match_name"],
            "market":         b["market"],
            "outcome":        b["outcome"],
            "profit_nok":     b["profit_nok"],
            "odds":           b["ref_odds"],
            "settled_at":     b["settled_at"],
        })
    return history


def get_summary(starting_bankroll: float = 10_000.0) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, stake_nok, profit_nok, market, clv FROM model_bets WHERE status != 'void'"
        ).fetchall()

    total_staked = 0.0
    total_profit = 0.0
    n_won = n_lost = n_pending = 0
    clv_total = 0.0
    n_clv = 0
    by_market: dict[str, dict] = {}

    for b in rows:
        mkt = b["market"]
        if mkt not in by_market:
            by_market[mkt] = {"n_won": 0, "n_lost": 0, "n_pending": 0, "profit": 0.0, "staked": 0.0}
        if b["status"] == "pending":
            n_pending += 1
            by_market[mkt]["n_pending"] += 1
        else:
            stake = b["stake_nok"] or 0
            pnl   = b["profit_nok"] or 0
            total_staked += stake
            total_profit += pnl
            by_market[mkt]["staked"] += stake
            by_market[mkt]["profit"] += pnl
            if b["status"] == "won":
                n_won += 1
                by_market[mkt]["n_won"] += 1
            else:
                n_lost += 1
                by_market[mkt]["n_lost"] += 1
            if b["clv"] is not None:
                clv_total += b["clv"]
                n_clv += 1

    n_settled = n_won + n_lost
    hit_rate  = round(n_won / n_settled * 100, 1) if n_settled > 0 else None
    roi       = round(total_profit / total_staked * 100, 2) if total_staked > 0 else None
    avg_clv   = round(clv_total / n_clv * 100, 2) if n_clv > 0 else None

    return {
        "starting_bankroll": starting_bankroll,
        "current_bankroll":  round(starting_bankroll + total_profit, 2),
        "total_staked":      round(total_staked, 2),
        "total_profit":      round(total_profit, 2),
        "roi":               roi,
        "n_won":             n_won,
        "n_lost":            n_lost,
        "n_pending":         n_pending,
        "hit_rate":          hit_rate,
        "avg_clv":           avg_clv,
        "by_market":         by_market,
    }
