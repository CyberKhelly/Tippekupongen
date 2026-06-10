"""
Phase 6B/C: Pool value analytics for NT Tippekupongen.

NT Tippekupongen is a parimutuel pool:
    payout = (omsetning × prize_rate) / n_winners

Key functions:
    compute_value_index()      — model_prob / public_prob per outcome
    compute_p_win()            — exact probability our coupon wins all 12
    compute_pool_value_ratio() — expected payout multiplier vs average ticket
    simulate_payout()          — Monte Carlo payout distribution (requires omsetning)

All payout figures are estimates — label clearly in the UI.
CLV and historical calibration require real closing odds (separate system).
"""
from __future__ import annotations
import random
from models.match import Match


# ─────────────────────────────────────────────────────────────────────────────
# Per-outcome metrics
# ─────────────────────────────────────────────────────────────────────────────

def compute_value_index(prob: float, pub_prob: float | None) -> float | None:
    """
    Value index for one outcome: model_prob / public_prob.

    Interpretation:
      1.00 — neutral (model and crowd agree)
      1.10 — slight value (+10% better than crowd expects)
      1.25 — good value
      1.50 — strong value
      2.00+ — extreme value (crowd heavily underweights this outcome)
      <1.00 — crowd overweights this outcome (negative pool value)

    Returns None when public_prob is below 2% — division becomes unreliable
    at very small public fractions.
    Capped at 5.0 for display stability.
    """
    if pub_prob is None or pub_prob < 0.02:
        return None
    return min(5.0, round(prob / pub_prob, 2))


# ─────────────────────────────────────────────────────────────────────────────
# Coupon-level analytics
# ─────────────────────────────────────────────────────────────────────────────

def compute_p_win(matches: list[Match], coupon: dict[int, list[str]]) -> float:
    """
    Exact probability that all 12 actual outcomes fall within our covered picks.

        P_win = Π_i  Σ_{X ∈ picks_i}  model_prob_{X,i}

    For a single-pick match this reduces to the model probability of that pick.
    For a halvdekk it is the sum of the top two outcome probabilities.
    For a full cover it is always 1.0 per match.

    This is deterministic — no simulation required.
    """
    p = 1.0
    for m in matches:
        picks = coupon.get(m.number, [])
        p_covered = sum(
            m.prob_h if o == "H" else m.prob_u if o == "U" else m.prob_b
            for o in picks
        )
        p *= p_covered
    return round(p, 6)


def compute_pool_value_ratio(
    matches: list[Match],
    coupon: dict[int, list[str]],
) -> float | None:
    """
    Payout multiplier over the average public ticket:
        PVR = P_model_win / P_public_win

    >1.0 — positive pool edge (our combination is underrepresented among likely winners)
    <1.0 — negative edge (crowd plays the same picks we do)

    Matches without public tip data contribute neutrally (P_public = P_model for
    those matches) so they neither help nor hurt the ratio.

    Returns None when fewer than 6 of the 12 matches have public data — the
    estimate is too unreliable to display.
    """
    p_model  = 1.0
    p_public = 1.0
    n_public = 0

    for m in matches:
        picks = coupon.get(m.number, [])

        model_sum = sum(
            m.prob_h if o == "H" else m.prob_u if o == "U" else m.prob_b
            for o in picks
        )
        p_model *= model_sum

        if m.has_public_tips:
            n_public += 1
            pub_sum = sum(
                (m.pub_prob_h or 1 / 3) if o == "H"
                else (m.pub_prob_u or 1 / 3) if o == "U"
                else (m.pub_prob_b or 1 / 3)
                for o in picks
            )
        else:
            pub_sum = model_sum   # neutral: no public data → assume crowd agrees
        p_public *= pub_sum

    if n_public < 6 or p_public < 1e-15:
        return None
    return round(p_model / p_public, 3)


# ─────────────────────────────────────────────────────────────────────────────
# Monte Carlo payout simulation
# ─────────────────────────────────────────────────────────────────────────────

def simulate_payout(
    matches: list[Match],
    coupon: dict[int, list[str]],
    n_rows: int,
    omsetning: float,
    prize_rate: float = 0.52,
    cost_per_row: float = 1.0,
    n_sims: int = 20_000,
    seed: int = 42,
) -> dict:
    """
    Monte Carlo payout simulation for NT Tippekupongen.

    Algorithm per draw:
      1. Sample one outcome per match from model probabilities.
      2. Check whether our coupon wins (every match outcome within covered picks).
      3. For winning draws: estimate competing public tickets using public probs.
      4. payout = (omsetning × prize_rate) / (e_public_winners + n_rows).

    Returns dict with payout statistics over winning draws.
    Empty dict (n_winning_sims=0) when zero winning draws are observed.

    Limitations:
      - omsetning is user-provided or assumed; actual NT turnover may differ
      - prize_rate of 0.52 is approximate (NT varies by week and prize tier)
      - public tip % approximates distribution of all tickets, not just singles
      - simulation treats our coverage uniformly (all n_rows share the same
        coverage pattern even though internal row structure varies)

    All figures should be displayed as estimates with a clear disclaimer.
    """
    rng = random.Random(seed)
    total_tickets = omsetning / cost_per_row

    payouts: list[float] = []

    for _ in range(n_sims):
        # ── Sample outcome from model ─────────────────────────────────────────
        outcome: dict[int, str] = {}
        for m in matches:
            r = rng.random()
            if r < m.prob_h:
                outcome[m.number] = "H"
            elif r < m.prob_h + m.prob_u:
                outcome[m.number] = "U"
            else:
                outcome[m.number] = "B"

        # ── Check if our coupon covers this outcome ───────────────────────────
        if not all(outcome[mn] in coupon[mn] for mn in coupon):
            continue

        # ── Estimate public competitors for this exact outcome ────────────────
        p_public_this = 1.0
        for m in matches:
            act = outcome[m.number]
            if m.has_public_tips:
                if act == "H":
                    pp = m.pub_prob_h or 1 / 3
                elif act == "U":
                    pp = m.pub_prob_u or 1 / 3
                else:
                    pp = m.pub_prob_b or 1 / 3
            else:
                pp = 1 / 3   # no public data — assume equal split
            p_public_this *= pp

        e_public_winners = total_tickets * p_public_this
        prize_pool = omsetning * prize_rate
        payout = prize_pool / max(1.0, e_public_winners + n_rows)
        payouts.append(payout)

    if not payouts:
        return {"n_winning_sims": 0, "p_win_simulated": 0.0}

    payouts.sort()
    n = len(payouts)
    return {
        "n_winning_sims": n,
        "p_win_simulated": round(n / n_sims, 4),
        "min":    round(payouts[0]),
        "p10":    round(payouts[n // 10]) if n >= 10 else round(payouts[0]),
        "median": round(payouts[n // 2]),
        "p90":    round(payouts[min(9 * n // 10, n - 1)]),
        "max":    round(payouts[-1]),
        "mean":   round(sum(payouts) / n),
    }
