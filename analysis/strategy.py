"""
Phase 6C: Strategy configuration for coupon generation.

Three modes control how the optimizer balances model confidence against
pool value signals when deciding coverage depth, system shape, and
halvdekk second picks.

Safe:     pure model confidence — maximise P(12/12)
Balanced: VI-adjusted confidence — mild contrarian halvdekk allowed
Jackpot:  strongest CDS influence — converts heldekk to halvdekk, maximises PVR

Composite score formula (lower = receives deeper coverage):
  Safe:     confidence
  Balanced: confidence × clip(VI_at_pick, 0.75, 1.25)
  Jackpot:  confidence − 0.35 × (CDS/50)

Shape objective:
  Safe:     maximise P(12/12)
  Balanced: maximise P(12/12)^0.9 × PVR^0.1
  Jackpot:  maximise PVR  (P(12/12) ≥ min_p_win_floor)

Invariants all modes must preserve:
  - Recommended single pick is ALWAYS the highest model-probability outcome
  - Full covers always include all three outcomes
  - No halvdekk second pick below min_prob_threshold
  - Model probabilities are never modified by strategy
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    display_name: str

    # ── Coverage ranking ────────────────────────────────────────────────────────
    cds_weight: float          # weight on CDS/50 subtracted from composite score
                               # 0 = ignore CDS (Safe/Balanced); >0 = high-CDS gets more coverage
    effective_conf_adj: float  # only used by Balanced: tiny value_top nudge (±pp fraction)

    # ── Shape selection ─────────────────────────────────────────────────────────
    shape_p_win_exp: float        # exponent on P(12/12) in shape objective (0 = ignore)
    shape_pvr_exp: float          # exponent on PVR in shape objective (0 = ignore)
    min_p_win_floor: float        # shapes with P(12/12) below this are excluded
    shape_min_utilization: float  # minimum rows / max_rows — prevents near-empty coupons

    # ── Halvdekk second pick ────────────────────────────────────────────────────
    min_prob_threshold: float       # minimum model probability for any halvdekk pick
    contrarian_pp_tolerance: float  # max prob gap (fraction) between #2 and #3 for substitution
    pick_vi_advantage: float        # VI of #3 must exceed VI of #2 by at least this


STRATEGIES: dict[str, StrategyConfig] = {
    "safe": StrategyConfig(
        name="safe",
        display_name="Safe",
        cds_weight=0.000,
        effective_conf_adj=0.000,
        shape_p_win_exp=1.0,
        shape_pvr_exp=0.0,
        min_p_win_floor=0.0,
        shape_min_utilization=0.50,
        min_prob_threshold=0.18,
        contrarian_pp_tolerance=0.00,   # never substitute
        pick_vi_advantage=999.0,
    ),
    "balanced": StrategyConfig(
        name="balanced",
        display_name="Balansert",
        cds_weight=0.000,
        effective_conf_adj=0.030,       # ±3pp nudge on value_top direction
        shape_p_win_exp=0.9,
        shape_pvr_exp=0.1,
        min_p_win_floor=0.0,
        shape_min_utilization=0.99,     # always use budget-filling shape (current behaviour)
        min_prob_threshold=0.18,
        contrarian_pp_tolerance=0.04,   # allow within 4pp gap
        pick_vi_advantage=0.20,
    ),
    "jackpot": StrategyConfig(
        name="jackpot",
        display_name="Jackpot",
        cds_weight=0.350,               # CDS/50 × 0.35 — dominant signal
        effective_conf_adj=0.000,
        shape_p_win_exp=0.0,            # pure PVR maximisation
        shape_pvr_exp=1.0,
        min_p_win_floor=0.003,          # never accept < 0.3% chance of winning
        shape_min_utilization=0.50,
        min_prob_threshold=0.12,
        contrarian_pp_tolerance=0.15,   # allow within 15pp gap
        pick_vi_advantage=0.05,         # any meaningful VI advantage is enough
    ),
}

DEFAULT_STRATEGY = "balanced"
