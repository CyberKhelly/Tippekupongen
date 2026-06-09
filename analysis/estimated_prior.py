"""
Model-Estimated Prior — fallback when bookmaker odds are absent.

Computes H/U/B probabilities from available statistical signals:
  - NT expert tips (60% weight when available — strongest signal)
  - Form last 5 (from fixture_stat_enrichment)
  - League standings position
  - Season goal difference
  - Home/away records

This is NOT bookmaker odds.  Do NOT:
  - Store in the odds or odds_snapshots tables
  - Use for CLV calculation
  - Label as bookmaker odds in the UI

Storage: fixture_estimated_prior table with source='model_estimated'

Entry point: compute_estimated_prior(enrichment_row: dict) -> dict | None
"""
from __future__ import annotations

# Base rates for Norwegian domestic football (lower / mid tier).
# Empirically, 3rd-division home win rate is lower than top-flight.
_BASE_H = 0.40
_BASE_U = 0.27
_BASE_B = 0.33

# Maximum |stats adjustment| on H (opposite sign applied to B)
_MAX_SHIFT = 0.15

# Expert tips weight when available
_W_EXPERT = 0.60
_W_STATS  = 0.40


def compute_estimated_prior(enrichment: dict) -> dict | None:
    """
    Estimate H/U/B probabilities when no bookmaker odds are present.

    enrichment — any dict that contains keys from fixture_stat_enrichment
                 joined with coupon_fixtures (including expert_h/u/b,
                 public_h/u/b, home_last_5, home_position, etc.)

    Returns:
        {
          'estimated_h': float,
          'estimated_u': float,
          'estimated_b': float,
          'signals_used': list[str],
          'confidence': float,      # 0.0–1.0
          'source': 'model_estimated',
        }
    or None when no signals are available at all.
    """
    from analysis.model import _compute_stats_signal, _get_float

    signals_used: list[str] = []

    # ── Step 1: stats-based home_edge ────────────────────────────────────────
    home_edge, stat_signals = _compute_stats_signal(enrichment)
    signals_used.extend(stat_signals)

    if stat_signals:
        shift = home_edge * _MAX_SHIFT
        raw_h = max(0.10, min(0.80, _BASE_H + shift))
        raw_b = max(0.10, min(0.80, _BASE_B - shift))
        raw_u = _BASE_U
        total = raw_h + raw_u + raw_b
        p_h = raw_h / total
        p_u = raw_u / total
        p_b = raw_b / total
    else:
        p_h, p_u, p_b = _BASE_H, _BASE_U, _BASE_B

    confidence = 0.35 if stat_signals else 0.20

    # ── Step 2: blend NT expert tips (dominant signal for lower leagues) ─────
    ex_h = _get_float(enrichment, "expert_h")
    ex_u = _get_float(enrichment, "expert_u")
    ex_b = _get_float(enrichment, "expert_b")

    if ex_h is not None and ex_u is not None and ex_b is not None:
        ex_sum = ex_h + ex_u + ex_b
        if ex_sum > 0:
            ex_h_n = ex_h / ex_sum
            ex_u_n = ex_u / ex_sum
            ex_b_n = ex_b / ex_sum

            p_h = _W_STATS * p_h + _W_EXPERT * ex_h_n
            p_u = _W_STATS * p_u + _W_EXPERT * ex_u_n
            p_b = _W_STATS * p_b + _W_EXPERT * ex_b_n

            # Float safety normalise
            total = p_h + p_u + p_b
            p_h /= total
            p_u /= total
            p_b /= total

            confidence = 0.65 if stat_signals else 0.50
            signals_used.append("nt_expert")

    if not signals_used:
        return None

    return {
        "estimated_h":  round(p_h, 4),
        "estimated_u":  round(p_u, 4),
        "estimated_b":  round(p_b, 4),
        "signals_used": signals_used,
        "confidence":   round(confidence, 2),
        "source":       "model_estimated",
    }
