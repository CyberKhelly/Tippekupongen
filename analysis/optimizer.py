"""
Phase 6C: Strategy-aware coupon optimizer.

Two-stage process:
  1. Composite score — sort matches by strategy-specific score (lower = more coverage)
  2. Shape search    — score every valid (n_full, n_half) pair by strategy objective,
                       pick the best

Composite score (lower → receives deeper coverage):
  Safe:     confidence
  Balanced: confidence + tiny value_top nudge (backward-compatible)
  Value:    confidence − 0.20 × (CDS/50)
  Jackpot:  confidence − 0.35 × (CDS/50)

  CDS (crowd_disagreement_score, 0–50pp) causes high-disagreement matches to
  receive more coverage under Value/Jackpot regardless of raw confidence.

Shape objective:
  Safe:     maximise P(12/12)
  Balanced: maximise P(12/12)^0.9 × PVR^0.1
  Value:    maximise P(12/12)^0.6 × PVR^0.4
  Jackpot:  maximise PVR  (subject to P(12/12) ≥ min_p_win_floor)

  Jackpot may therefore prefer (0 heldekk, N halvdekk) over the standard shape
  because halvdekk on an uncertain match yields positive PVR whereas heldekk is
  pool-neutral (covers everything, so no differentiation).

Invariants across all strategies:
  - Single picks always use the highest model-probability outcome
  - Full covers always include all three outcomes
  - Budget constraint (rows ≤ max_rows) is never violated
  - Model probabilities are read-only; strategy never writes to Match fields

Backward compatibility:
  - _effective_confidence() is kept for verify_model.py imports
  - strategy="balanced" with default budget reproduces Phase-5 shape in most cases
"""
from __future__ import annotations
from models.match import Match
from analysis.strategy import StrategyConfig, STRATEGIES
from analysis.pool_value import compute_p_win, compute_pool_value_ratio


# ─────────────────────────────────────────────────────────────────────────────
# Phase-5 compatibility shim (kept for external imports)
# ─────────────────────────────────────────────────────────────────────────────

def _effective_confidence(m: Match) -> float:
    """
    Phase-5 confidence nudge for crowd value signals.
    Preserved for backward compatibility — imported by verify_model.py.
    """
    conf = m.confidence
    if not m.has_public_tips:
        return conf
    vals      = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
    top_value = vals.get(m.recommendation)
    if top_value is None:
        return conf
    if top_value > 10.0:
        return min(conf + 0.02, 1.0)
    if top_value < -15.0:
        return max(conf - 0.02, 0.0)
    return conf


# ─────────────────────────────────────────────────────────────────────────────
# Composite score — determines coverage ranking
# ─────────────────────────────────────────────────────────────────────────────

def _composite_score(m: Match, cfg: StrategyConfig) -> float:
    """
    Lower score → match receives deeper coverage.

    Safe:     pure model confidence — ignores all crowd signals
    Balanced: tiny directional nudge when public over/underplays model pick
    Value:    CDS-penalised confidence — high disagreement → promoted toward coverage
    Jackpot:  stronger CDS penalty — crowd disagreement is the primary coverage driver
    """
    conf = m.confidence

    if cfg.name == "safe":
        return conf

    if cfg.name == "balanced":
        if not m.has_public_tips:
            return conf
        vals      = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
        top_value = vals.get(m.recommendation) or 0.0
        v_norm    = max(-1.0, min(1.0, top_value / 20.0))
        return max(0.0, min(1.0, conf + cfg.effective_conf_adj * v_norm))

    # Value / Jackpot: CDS-based reduction
    cds      = m.crowd_disagreement_score or 0.0
    cds_norm = min(1.0, cds / 50.0)
    return max(0.0, conf - cfg.cds_weight * cds_norm)


# ─────────────────────────────────────────────────────────────────────────────
# Halvdekk second-pick selection
# ─────────────────────────────────────────────────────────────────────────────

def _pick_halvdekk(m: Match, cfg: StrategyConfig) -> list[str]:
    """
    Choose 2 outcomes for a halvdekk row.

    Safe: always top-2 by model probability.

    Balanced/Value/Jackpot: may substitute #3 for #2 when ALL:
      (a) prob gap between #2 and #3 ≤ contrarian_pp_tolerance
      (b) #3 probability ≥ min_prob_threshold
      (c) value_index of #3 exceeds value_index of #2 by ≥ pick_vi_advantage

    The top pick (#1 by probability) is NEVER substituted.
    """
    probs = sorted(
        [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
        key=lambda x: x[1],
        reverse=True,
    )
    top_out, _      = probs[0]
    sec_out, sec_p  = probs[1]
    thr_out, thr_p  = probs[2]

    if cfg.contrarian_pp_tolerance == 0.0 or not m.has_public_tips:
        return sorted([top_out, sec_out])

    value_map = {"H": m.value_h, "U": m.value_u, "B": m.value_b}

    def _vi(outcome: str, p: float) -> float:
        val_pp = value_map.get(outcome)
        if val_pp is None:
            return 1.0
        pub_p = p - val_pp / 100.0
        if pub_p < 0.01:
            return min(5.0, p / 0.01)
        return min(5.0, p / pub_p)

    vi_sec = _vi(sec_out, sec_p)
    vi_thr = _vi(thr_out, thr_p)

    gap_ok       = (sec_p - thr_p) <= cfg.contrarian_pp_tolerance
    floor_ok     = thr_p >= cfg.min_prob_threshold
    value_better = (vi_thr - vi_sec) >= cfg.pick_vi_advantage

    if gap_ok and floor_ok and value_better:
        return sorted([top_out, thr_out])

    return sorted([top_out, sec_out])


# ─────────────────────────────────────────────────────────────────────────────
# Build a full coupon from a sorted match list and a (nf, nh) shape
# ─────────────────────────────────────────────────────────────────────────────

def _build_coupon(
    ranked: list[Match],
    n_full: int,
    n_half: int,
    cfg: StrategyConfig,
) -> dict[int, list[str]]:
    """
    Assign coverage and build picks for one candidate (n_full, n_half) shape.
    ranked is pre-sorted by composite score ascending (lowest score → most coverage).
    """
    coupon: dict[int, list[str]] = {}
    for i, m in enumerate(ranked):
        if i < n_full:
            coupon[m.number] = ["H", "U", "B"]
        elif i < n_full + n_half:
            coupon[m.number] = _pick_halvdekk(m, cfg)
        else:
            probs = sorted(
                [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
                key=lambda x: x[1],
                reverse=True,
            )
            coupon[m.number] = [probs[0][0]]
    return coupon


# ─────────────────────────────────────────────────────────────────────────────
# Main optimizer entry point
# ─────────────────────────────────────────────────────────────────────────────

def optimize_coupon(
    matches: list[Match],
    budget_nok: float,
    cost_per_row: float = 1.0,
    strategy: str = "balanced",
) -> tuple[dict[int, list[str]], int]:
    """
    Strategy-aware Tippekupongen coupon optimizer (Phase 6C).

    Searches all valid (n_full, n_half) pairs using rows ≥ budget × 0.50 and
    scores each by the strategy's shape objective. Returns the best-scoring
    coupon and its row count.

    Shape candidates for 192 NOK budget (50% floor = 96 rows):
        (0,7)=128  (1,5)=96  (1,6)=192  (2,4)=144  (3,2)=108  (4,1)=162

    Expected differentiation (192 NOK):
        Safe:     (1,6) — P(win) maximised
        Balanced: (1,6) — small PVR tilt, same shape in most cases
        Value:    (1,6) — different matches get coverage (CDS-driven ranking)
        Jackpot:  (0,7) — no heldekk; Frigg halvdekk outscores heldekk on PVR
    """
    cfg      = STRATEGIES.get(strategy, STRATEGIES["balanced"])
    max_rows = max(1, int(budget_nok / cost_per_row))
    min_rows = max(1, int(max_rows * cfg.shape_min_utilization))
    n        = len(matches)

    # ── Step 1: sort matches by composite score (fixed per strategy) ──────────
    ranked = sorted(matches, key=lambda m: _composite_score(m, cfg))

    # ── Step 2: enumerate candidate shapes ───────────────────────────────────
    candidates: list[tuple[int, int, int]] = []   # (rows, nf, nh)
    for nf in range(n + 1):
        for nh in range(n - nf + 1):
            rows = (3 ** nf) * (2 ** nh)
            if min_rows <= rows <= max_rows:
                candidates.append((rows, nf, nh))

    if not candidates:
        # Fallback: accept best shape regardless of utilisation floor
        best_rows, best_nf, best_nh = 1, 0, 0
        for nf in range(n + 1):
            for nh in range(n - nf + 1):
                rows = (3 ** nf) * (2 ** nh)
                if rows <= max_rows and rows > best_rows:
                    best_rows, best_nf, best_nh = rows, nf, nh
        coupon = _build_coupon(ranked, best_nf, best_nh, cfg)
        return coupon, best_rows

    # ── Step 3: score each candidate shape by strategy objective ─────────────
    best_obj  = -1.0
    best_rows = candidates[0][0]
    best_nf   = candidates[0][1]
    best_nh   = candidates[0][2]

    for rows, nf, nh in candidates:
        coupon = _build_coupon(ranked, nf, nh, cfg)
        p_win  = compute_p_win(matches, coupon)

        if cfg.min_p_win_floor > 0.0 and p_win < cfg.min_p_win_floor:
            continue   # hard floor — skip this shape

        pvr = compute_pool_value_ratio(matches, coupon)
        if pvr is None:
            pvr = 1.0   # neutral when insufficient public data

        p_exp = cfg.shape_p_win_exp
        v_exp = cfg.shape_pvr_exp

        if p_exp == 0.0:
            obj = pvr ** v_exp if v_exp > 0.0 else 1.0
        elif v_exp == 0.0:
            obj = p_win ** p_exp
        else:
            obj = (p_win ** p_exp) * (pvr ** v_exp)

        if obj > best_obj:
            best_obj  = obj
            best_rows = rows
            best_nf   = nf
            best_nh   = nh

    coupon = _build_coupon(ranked, best_nf, best_nh, cfg)
    return coupon, best_rows
