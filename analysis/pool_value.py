"""
Phase 6B/C: Pool value analytics for NT Tippekupongen.
Phase 7:    Corrected payout simulator.

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
import math
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
# Monte Carlo payout simulation — Phase 7 (corrected)
# ─────────────────────────────────────────────────────────────────────────────

def _poisson_sample(rng: random.Random, lam: float) -> int:
    """
    One sample from Poisson(lam).
    Knuth algorithm for lam <= 200; Gaussian approximation for larger values.
    """
    if lam <= 0:
        return 0
    if lam > 200:
        return max(0, round(lam + math.sqrt(lam) * rng.gauss(0.0, 1.0)))
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while p > L:
        k += 1
        p *= rng.random()
    return k - 1


def _pub_probs(m: Match) -> tuple[float, float, float]:
    """Normalised public H/U/B fractions; returns (1/3, 1/3, 1/3) if unavailable."""
    if not m.has_public_tips:
        return 1 / 3, 1 / 3, 1 / 3
    h = m.pub_prob_h or 0.0
    u = m.pub_prob_u or 0.0
    b = m.pub_prob_b or 0.0
    total = h + u + b
    if total < 0.01:
        return 1 / 3, 1 / 3, 1 / 3
    return h / total, u / total, b / total


def _sim_narrative(
    e_winners: float,
    pvr: float | None,
    n_underplayed_singles: int,
) -> str:
    """Short explanation of why the median payout is high or low."""
    parts: list[str] = []

    if e_winners < 100:
        parts.append(f"Sjeldent utfall — ~{round(e_winners)} rekker deler potten ved gevinst.")
    elif e_winners < 1_000:
        parts.append(f"~{round(e_winners)} rekker deler potten ved gevinst i snitt.")
    else:
        parts.append(f"~{round(e_winners):,} rekker deler potten ved gevinst i snitt.")

    if pvr is not None:
        if pvr >= 3.0:
            parts.append(
                f"PVR {pvr:.1f}x: kupongen er {pvr:.1f}x mer unik enn en tilfeldig rekke."
            )
        elif pvr >= 1.5:
            parts.append(f"PVR {pvr:.1f}x: kupongen er noe mer unik enn gjennomsnittet.")
        elif pvr < 0.9:
            parts.append(
                f"PVR {pvr:.1f}x: kupongen ligner folkerts valg — lav eksklusivitet."
            )

    if n_underplayed_singles >= 3:
        parts.append(f"{n_underplayed_singles} av singelvalgene er underspilt av folket.")
    elif n_underplayed_singles >= 1:
        parts.append(f"{n_underplayed_singles} singeltips er underspilt av folket.")

    return " ".join(parts)


def simulate_payout(
    matches: list[Match],
    coupon: dict[int, list[str]],
    n_rows: int,
    omsetning: float,
    prize_rate: float = 0.52,
    cost_per_row: float = 1.0,
    n_sims: int = 50_000,
    seed: int = 42,
) -> dict:
    """
    Monte Carlo payout simulation for NT Tippekupongen (Phase 7).

    NT is a parimutuel pool — the prize is shared equally among all winning rows.
    For any specific 12-match outcome, exactly 1 of our rows can match it.

    Algorithm per simulation:
      1. Sample one outcome per match from model probabilities.
      2. Check whether our coupon covers this outcome.
      3. Compute p_public(outcome) = product of normalised public tip fractions.
      4. Sample other_winners ~ Poisson((N - n_rows) * p_public)  [stochastic].
      5. payout = prize_pool / max(1, other_winners + 1).

    Corrections vs prior version:
      - Our contribution is +1 winning row (not +n_rows): for any specific
        outcome only one row in our system matches it.
      - Other winners use (N - n_rows) to exclude our rows from the pool.
      - Poisson sampling adds realistic variance in the winner count.

    Returns statistics over winning simulations and an explanatory narrative.
    Returns {"n_winning_sims": 0} when no wins are observed in n_sims draws.

    All figures are estimates. Actual NT payouts depend on real omsetning,
    prize tier, winner count, and NT's prize allocation rules.
    """
    rng        = random.Random(seed)
    N          = omsetning / cost_per_row        # total rows in pool
    prize_pool = omsetning * prize_rate
    n_other    = max(0.0, N - n_rows)            # other rows (ours excluded)

    payouts:       list[float] = []
    winner_counts: list[int]   = []

    for _ in range(n_sims):
        # ── Step 1: sample outcome from model ────────────────────────────────
        outcome: dict[int, str] = {}
        for m in matches:
            r = rng.random()
            if r < m.prob_h:
                outcome[m.number] = "H"
            elif r < m.prob_h + m.prob_u:
                outcome[m.number] = "U"
            else:
                outcome[m.number] = "B"

        # ── Step 2: check if our coupon covers this outcome ──────────────────
        if not all(outcome[mn] in coupon[mn] for mn in coupon):
            continue

        # ── Step 3: public probability of this exact 12-match outcome ────────
        p_pub = 1.0
        for m in matches:
            ph, pu, pb = _pub_probs(m)
            act = outcome[m.number]
            p_pub *= ph if act == "H" else (pu if act == "U" else pb)

        # ── Step 4: stochastic other-winner count ─────────────────────────────
        w_others = _poisson_sample(rng, n_other * p_pub)

        # ── Step 5: payout for our 1 winning row ─────────────────────────────
        total_winners = w_others + 1
        payout        = prize_pool / max(1.0, total_winners)

        payouts.append(payout)
        winner_counts.append(total_winners)

    if not payouts:
        return {"n_winning_sims": 0, "p_win_simulated": 0.0}

    payouts.sort()
    n_w        = len(payouts)
    e_winners  = round(sum(winner_counts) / len(winner_counts))

    pvr = compute_pool_value_ratio(matches, coupon)
    n_underplayed = sum(
        1 for m in matches
        if len(coupon.get(m.number, [])) == 1
        and m.has_public_tips
        and ({"H": m.value_h, "U": m.value_u, "B": m.value_b}
             .get(coupon[m.number][0]) or 0.0) > 0
    )

    return {
        "n_winning_sims":  n_w,
        "p_win_simulated": round(n_w / n_sims, 4),
        "min":      round(payouts[0]),
        "p10":      round(payouts[n_w // 10]) if n_w >= 10 else round(payouts[0]),
        "median":   round(payouts[n_w // 2]),
        "p90":      round(payouts[min(9 * n_w // 10, n_w - 1)]),
        "p99":      round(payouts[min(99 * n_w // 100, n_w - 1)]),
        "max":      round(payouts[-1]),
        "mean":     round(sum(payouts) / n_w),
        "e_winners": e_winners,
        "narrative": _sim_narrative(e_winners, pvr, n_underplayed),
    }
