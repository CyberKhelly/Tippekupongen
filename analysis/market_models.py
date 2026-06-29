"""
Poisson-based market probability models for BTTS and Over/Under.

Uses venue-specific goal averages from Phase 13 enrichment (preferred)
or overall averages from Phase 10 as fallback.
"""
from __future__ import annotations
import math


def _poisson_pmf(k: int, mu: float) -> float:
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return (mu ** k) * math.exp(-mu) / math.factorial(k)


def expected_goals(
    home_avg_for: float | None,
    home_avg_against: float | None,
    away_avg_for: float | None,
    away_avg_against: float | None,
) -> tuple[float, float]:
    """
    Dixon-Coles-style expected goals from seasonal averages.
    xg_home = (home_team_home_scoring + away_team_away_conceding) / 2
    xg_away = (away_team_away_scoring + home_team_home_conceding) / 2
    Returns (xg_home, xg_away) with sensible minimums.
    """
    if home_avg_for is not None and away_avg_against is not None:
        xg_home = (home_avg_for + away_avg_against) / 2
    else:
        xg_home = 1.4   # European average

    if away_avg_for is not None and home_avg_against is not None:
        xg_away = (away_avg_for + home_avg_against) / 2
    else:
        xg_away = 1.1

    return max(xg_home, 0.1), max(xg_away, 0.05)


def btts_probability(xg_home: float, xg_away: float) -> float:
    """P(home ≥ 1) × P(away ≥ 1) under independent Poisson."""
    p_home = 1 - _poisson_pmf(0, xg_home)
    p_away = 1 - _poisson_pmf(0, xg_away)
    return round(p_home * p_away, 4)


def over_under_probability(xg_home: float, xg_away: float, line: float = 2.5) -> tuple[float, float]:
    """
    Joint Poisson probability for total goals over/under a line.
    Returns (p_over, p_under).
    """
    threshold = int(math.floor(line))
    p_under = 0.0
    cap = 15
    for h in range(cap + 1):
        ph = _poisson_pmf(h, xg_home)
        for a in range(cap + 1 - h):
            if h + a <= threshold:
                p_under += ph * _poisson_pmf(a, xg_away)
    p_over = max(0.0, 1.0 - p_under)
    return round(p_over, 4), round(p_under, 4)


def win_draw_loss_probability(xg_home: float, xg_away: float) -> tuple[float, float, float]:
    """
    P(home_win), P(draw), P(away_win) under independent Poisson.
    Normalised to sum to 1.0.
    """
    cap = 14
    p_h = p_d = p_a = 0.0
    for h in range(cap + 1):
        ph = _poisson_pmf(h, xg_home)
        for a in range(cap + 1):
            pa = _poisson_pmf(a, xg_away)
            p = ph * pa
            if h > a:    p_h += p
            elif h == a: p_d += p
            else:        p_a += p
    total = p_h + p_d + p_a or 1.0
    return round(p_h / total, 4), round(p_d / total, 4), round(p_a / total, 4)


def market_probs_from_enrichment(e: dict) -> dict:
    """
    Derive BTTS and O/U 2.5 model probabilities from enrichment data.

    Priority: Phase 13 venue-specific → Phase 10 overall → European average.
    Returns fractions (0–1) for btts_yes, over_2_5, under_2_5,
    plus xg_home and xg_away for transparency.
    """
    # Phase 13 venue-specific (preferred)
    hgf = e.get("home_avg_goals_for_home")
    hga = e.get("home_avg_goals_against_home")
    agf = e.get("away_avg_goals_for_away")
    aga = e.get("away_avg_goals_against_away")

    # Phase 10 overall (fallback)
    if hgf is None: hgf = e.get("home_avg_goals_for")
    if hga is None: hga = e.get("home_avg_goals_against")
    if agf is None: agf = e.get("away_avg_goals_for")
    if aga is None: aga = e.get("away_avg_goals_against")

    # Guard: if all four are zero, we have no useful data
    has_data = any(v is not None and v > 0 for v in [hgf, hga, agf, aga])

    xg_home, xg_away = expected_goals(hgf, hga, agf, aga)
    btts = btts_probability(xg_home, xg_away)
    p_over, p_under = over_under_probability(xg_home, xg_away)

    return {
        "xg_home":    round(xg_home, 2),
        "xg_away":    round(xg_away, 2),
        "btts_yes":   btts,
        "btts_no":    round(1 - btts, 4),
        "over_2_5":   p_over,
        "under_2_5":  p_under,
        "has_data":   has_data,
    }
