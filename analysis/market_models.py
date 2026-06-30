"""
Poisson-based market probability models for BTTS and Over/Under.

Uses venue-specific goal averages from Phase 13 enrichment (preferred)
or overall averages from Phase 10 as fallback.
Bayesian shrinkage (k=6) applied to all raw xG estimates.
"""
from __future__ import annotations
import math
import re

_EU_HOME_XG = 1.40       # European-average xG for home team
_EU_AWAY_XG = 1.10       # European-average xG for away team
_SHRINK_K = 6             # Bayesian shrinkage constant (equivalent prior games)
_MIN_VENUE_SAMPLES = 5    # minimum venue-specific games to use venue averages


def _poisson_pmf(k: int, mu: float) -> float:
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return (mu ** k) * math.exp(-mu) / math.factorial(k)


def _parse_venue_games(record_str: str | None) -> int:
    """Parse total games from 'W4 D2 L1' style strings. Returns 0 on failure."""
    if not record_str:
        return 0
    return sum(int(n) for n in re.findall(r'\d+', record_str))


def shrink_xg(raw_xg: float, n_samples: int, global_mean: float, k: float = _SHRINK_K) -> float:
    """
    Bayesian shrinkage toward a global mean.
    weight = n / (n + k);  result = weight * raw + (1 - weight) * mean
    """
    w = n_samples / (n_samples + k)
    return w * raw_xg + (1 - w) * global_mean


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
    Callers should pre-shrink inputs; this function does not apply shrinkage.
    """
    if home_avg_for is not None and away_avg_against is not None:
        xg_home = (home_avg_for + away_avg_against) / 2
    else:
        xg_home = _EU_HOME_XG

    if away_avg_for is not None and home_avg_against is not None:
        xg_away = (away_avg_for + home_avg_against) / 2
    else:
        xg_away = _EU_AWAY_XG

    return max(xg_home, 0.1), max(xg_away, 0.05)


def btts_probability(xg_home: float, xg_away: float) -> float:
    """P(home >= 1) * P(away >= 1) under independent Poisson."""
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

    Priority: Phase 13 venue-specific (n >= 5) -> Phase 10 overall -> EU average.
    Bayesian shrinkage (k=6) toward EU average applied to all raw xG.

    Returns fractions (0-1) for btts_yes, over_2_5, under_2_5, plus audit fields:
      xg_home, xg_away, xg_home_raw, xg_away_raw,
      sample_size_home, sample_size_away, n_eff, shrinkage_weight, has_data.
    """
    n_home_venue = _parse_venue_games(e.get("home_home_record"))
    n_away_venue = _parse_venue_games(e.get("away_away_record"))

    # Use venue-specific (Phase 13) only when both sides have enough games
    if n_home_venue >= _MIN_VENUE_SAMPLES and n_away_venue >= _MIN_VENUE_SAMPLES:
        hgf_raw = e.get("home_avg_goals_for_home")
        hga_raw = e.get("home_avg_goals_against_home")
        agf_raw = e.get("away_avg_goals_for_away")
        aga_raw = e.get("away_avg_goals_against_away")
        n_eff = min(n_home_venue, n_away_venue)
    else:
        hgf_raw = hga_raw = agf_raw = aga_raw = None
        n_eff = min(
            int(e.get("home_played") or 0),
            int(e.get("away_played") or 0),
        )

    # Phase 10 overall fallback
    if hgf_raw is None: hgf_raw = e.get("home_avg_goals_for")
    if hga_raw is None: hga_raw = e.get("home_avg_goals_against")
    if agf_raw is None: agf_raw = e.get("away_avg_goals_for")
    if aga_raw is None: aga_raw = e.get("away_avg_goals_against")

    has_data = any(v is not None and v > 0 for v in [hgf_raw, hga_raw, agf_raw, aga_raw])

    if has_data:
        # Compute raw Dixon-Coles xG then shrink toward EU average
        raw_xg_home = (
            ((hgf_raw or _EU_HOME_XG) + (aga_raw or _EU_HOME_XG)) / 2
        )
        raw_xg_away = (
            ((agf_raw or _EU_AWAY_XG) + (hga_raw or _EU_AWAY_XG)) / 2
        )
        w = n_eff / (n_eff + _SHRINK_K)
        xg_home = max(w * raw_xg_home + (1 - w) * _EU_HOME_XG, 0.1)
        xg_away = max(w * raw_xg_away + (1 - w) * _EU_AWAY_XG, 0.05)
    else:
        raw_xg_home = raw_xg_away = None
        w = 0.0
        xg_home, xg_away = _EU_HOME_XG, _EU_AWAY_XG

    btts = btts_probability(xg_home, xg_away)
    p_over, p_under = over_under_probability(xg_home, xg_away)

    return {
        "xg_home":          round(xg_home, 2),
        "xg_away":          round(xg_away, 2),
        "xg_home_raw":      round(raw_xg_home, 2) if raw_xg_home is not None else None,
        "xg_away_raw":      round(raw_xg_away, 2) if raw_xg_away is not None else None,
        "btts_yes":         btts,
        "btts_no":          round(1 - btts, 4),
        "over_2_5":         p_over,
        "under_2_5":        p_under,
        "has_data":         has_data,
        "sample_size_home": n_home_venue,
        "sample_size_away": n_away_venue,
        "n_eff":            n_eff,
        "shrinkage_weight": round(w, 3),
    }
