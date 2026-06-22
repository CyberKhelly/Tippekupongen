"""
Model-Estimated Prior — fallback when bookmaker odds are absent.

Computes H/U/B probabilities from available statistical signals only:
  - Form last 5 (from fixture_stat_enrichment)
  - League standings position
  - Season goal difference
  - Home/away records

NT expert/public tips are NOT used — model probability must be independent
of NT percentages. Returns None when no statistical signals are available.

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


def compute_estimated_prior(enrichment: dict) -> dict | None:
    """
    Estimate H/U/B probabilities when no bookmaker odds are present.

    Uses only API-Football statistical signals — form, standings, goals,
    home/away record. NT expert/public percentages are intentionally excluded
    to keep model probability independent of NT tip data.

    enrichment — any dict that contains keys from fixture_stat_enrichment
                 (home_last_5, away_last_5, home_position, etc.)

    Returns:
        {
          'estimated_h': float,
          'estimated_u': float,
          'estimated_b': float,
          'signals_used': list[str],
          'confidence': float,      # 0.0–1.0
          'source': 'model_estimated',
        }
    or None when no AF statistical signals are available.
    """
    from analysis.model import _compute_stats_signal

    signals_used: list[str] = []

    # ── Stats-based home_edge (form, standings, goals, H/A record) ───────────
    home_edge, stat_signals = _compute_stats_signal(enrichment)
    signals_used.extend(stat_signals)

    if not signals_used:
        return None

    shift = home_edge * _MAX_SHIFT
    raw_h = max(0.10, min(0.80, _BASE_H + shift))
    raw_b = max(0.10, min(0.80, _BASE_B - shift))
    raw_u = _BASE_U
    total = raw_h + raw_u + raw_b
    p_h = raw_h / total
    p_u = raw_u / total
    p_b = raw_b / total

    return {
        "estimated_h":  round(p_h, 4),
        "estimated_u":  round(p_u, 4),
        "estimated_b":  round(p_b, 4),
        "signals_used": signals_used,
        "confidence":   round(0.35, 2),
        "source":       "model_estimated",
    }
