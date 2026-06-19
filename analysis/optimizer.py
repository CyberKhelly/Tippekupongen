"""
Phase 6C: Strategy-aware coupon optimizer.

Two-stage process:
  1. Composite score — sort matches by strategy-specific score (lower = more coverage)
  2. Shape search    — score every valid (n_full, n_half) pair by strategy objective,
                       pick the best

Composite score (lower → receives deeper coverage):
  Safe:     confidence
  Balanced: confidence × clip(VI_at_pick, 0.75, 1.25)  — VI = model_prob / pub_prob
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
import math
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
    Balanced: confidence × clip(VI_at_pick, 0.75, 1.25) — crowd-heavy picks penalised
    Value:    CDS-penalised confidence — high disagreement → promoted toward coverage
    Jackpot:  stronger CDS penalty — crowd disagreement is the primary coverage driver
    """
    conf = m.confidence

    if cfg.name == "safe":
        return conf

    if cfg.name == "balanced":
        if not m.has_public_tips:
            return conf
        pub_map = {"H": m.pub_prob_h or 0.0, "U": m.pub_prob_u or 0.0, "B": m.pub_prob_b or 0.0}
        pub_p   = pub_map.get(m.recommendation) or 0.0
        if pub_p < 0.01:
            return conf
        vi = conf / pub_p
        return conf * max(0.75, min(1.25, vi))

    # Value / Jackpot: CDS-based reduction
    cds      = m.crowd_disagreement_score or 0.0
    cds_norm = min(1.0, cds / 50.0)

    # Design A (Value only): suppress CDS promotion when halvdekk reduces pool value.
    # CDS signals crowd-model disagreement, but high disagreement on a strongly
    # underplayed single means halvdekk would dilute that edge rather than capture it.
    # Gate: only apply CDS reduction when halvdekk_ratio >= single_ratio.
    if cfg.name == "value" and cds_norm > 0.0 and m.has_public_tips:
        probs  = sorted(
            [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
            key=lambda x: x[1], reverse=True,
        )
        top_p, sec_p = probs[0][1], probs[1][1]
        top_o, sec_o = probs[0][0], probs[1][0]
        ph = m.pub_prob_h or 0.0
        pu = m.pub_prob_u or 0.0
        pb = m.pub_prob_b or 0.0
        _total = ph + pu + pb
        if _total > 0.01:
            _pmap  = {"H": ph / _total, "U": pu / _total, "B": pb / _total}
            pp_top = _pmap[top_o]
            pp_sec = _pmap[sec_o]
            if pp_top > 0.001 and (pp_top + pp_sec) > 0.001:
                if (top_p + sec_p) / (pp_top + pp_sec) < top_p / pp_top:
                    cds_norm = 0.0  # halvdekk hurts PVR — do not promote via CDS

    return max(0.0, conf - cfg.cds_weight * cds_norm)


# ─────────────────────────────────────────────────────────────────────────────
# Halvdekk second-pick selection
# ─────────────────────────────────────────────────────────────────────────────

def _pick_halvdekk(m: Match, cfg: StrategyConfig) -> list[str]:
    """
    Choose 2 outcomes for a halvdekk row.

    Safe: always top-2 by model probability.

    Balanced/Value: VI-substitution — may substitute #3 for #2 when ALL:
      (a) prob gap between #2 and #3 ≤ contrarian_pp_tolerance
      (b) #3 probability ≥ min_prob_threshold
      (c) value_index of #3 exceeds value_index of #2 by ≥ pick_vi_advantage
      Top outcome always included.

    Jackpot: tries all 3 pairs; picks highest log-PVR. Change A guard: when the
      natural pair (top + sec) is already pool-positive (PVR ≥ 1.0), requires a
      minimum gain of 0.08 log units (≈ 8% PVR factor) before switching to a
      potentially excludes-top pair. Prevents over-aggressive deviations on
      weakly-overcrowded matches (e.g. CDS=7.1pp, natural PVR=1.036, gain=0.057).
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

    # ── Jackpot: try all 3 pairs; pick the one with highest PVR contribution.
    # Allows halvdekk to exclude the top-probability outcome when the crowd
    # over-indexes on it (e.g. H at 66% public vs 51% model → U+B has better PVR).
    # Change A: requires minimum gain (0.08 log units ≈ 8% PVR factor) before
    # switching when the natural pair is already pool-positive. Prevents over-
    # aggressive excludes-top on weakly-overcrowded matches (e.g. Scotland:
    # CDS=7.1pp, natural PVR=1.036, gain=+0.057 — below the threshold).
    if cfg.name == "jackpot":
        _pm = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
        _pp = {
            "H": (m.pub_prob_h or m.prob_h),
            "U": (m.pub_prob_u or m.prob_u),
            "B": (m.pub_prob_b or m.prob_b),
        }
        best_pvr_pair: list[str] | None = None
        best_log_pvr = -999.0
        for a, b in (("H", "U"), ("H", "B"), ("U", "B")):
            if _pm[a] < cfg.min_prob_threshold or _pm[b] < cfg.min_prob_threshold:
                continue
            pub_s = _pp[a] + _pp[b]
            lv = math.log((_pm[a] + _pm[b]) / pub_s) if pub_s > 1e-9 else 0.0
            if lv > best_log_pvr:
                best_log_pvr = lv
                best_pvr_pair = sorted([a, b])
        if best_pvr_pair is not None:
            nat_pub_s = _pp[top_out] + _pp[sec_out]
            nat_log_pvr = (
                math.log((_pm[top_out] + _pm[sec_out]) / nat_pub_s)
                if nat_pub_s > 1e-9 else 0.0
            )
            if nat_log_pvr > 0.0 and (best_log_pvr - nat_log_pvr) < 0.08:
                return sorted([top_out, sec_out])
            return best_pvr_pair
        # Fallthrough: all pairs failed the probability floor — use standard logic

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
# Jackpot tie-breaker: halvdekk PVR benefit
# ─────────────────────────────────────────────────────────────────────────────

def _best_halvdekk_log_pvr(m: Match, cfg: StrategyConfig) -> float:
    """
    Best log(PVR factor) achievable by any valid halvdekk pair for this match.

    Used as a secondary sort key in Jackpot coverage ranking: when two matches
    have composite_scores within one bucket (0.01), the match where a halvdekk
    would contribute more PVR gets coverage priority.

    Returns 0.0 (neutral) when no valid pair exists or public data is absent.
    Pairs where either outcome falls below cfg.min_prob_threshold are skipped —
    matches the same floor enforced in _pick_halvdekk for Jackpot.
    """
    if not m.has_public_tips:
        return 0.0
    pm = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
    pp = {
        "H": (m.pub_prob_h or m.prob_h),
        "U": (m.pub_prob_u or m.prob_u),
        "B": (m.pub_prob_b or m.prob_b),
    }
    best = 0.0
    for a, b in (("H", "U"), ("H", "B"), ("U", "B")):
        if pm[a] < cfg.min_prob_threshold or pm[b] < cfg.min_prob_threshold:
            continue
        pub_s = pp[a] + pp[b]
        if pub_s < 1e-9:
            continue
        lv = math.log((pm[a] + pm[b]) / pub_s)
        if lv > best:
            best = lv
    return best


def _jackpot_coverage_key(m: Match, cfg: StrategyConfig) -> tuple[float, float]:
    """
    Two-level sort key for Jackpot coverage ranking.

    Primary:   composite_score rounded to the nearest 0.01 bucket.
               Preserves the CDS-driven ordering within each bucket.
    Secondary: negative best halvdekk log-PVR.
               Within a bucket, the match where a halvdekk contributes the most
               PVR is promoted toward coverage (gets more negative secondary key
               and therefore sorts earlier in ascending order).

    Bucket size 0.01 means scores must differ by less than 0.005 from the same
    0.01 midpoint to land in the same bucket — tight enough that only genuinely
    near-tied matches share a bucket.
    """
    _BUCKET = 0.01
    bucket = round(_composite_score(m, cfg) / _BUCKET) * _BUCKET
    return bucket, -_best_halvdekk_log_pvr(m, cfg)


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
    # Jackpot uses a two-level key: bucketed composite score (primary) + halvdekk
    # PVR benefit as tie-breaker. All other strategies use composite score only.
    if cfg.name == "jackpot":
        ranked = sorted(matches, key=lambda m: _jackpot_coverage_key(m, cfg))
    else:
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


# ─────────────────────────────────────────────────────────────────────────────
# Unconstrained anchor coupon + budget comparison
# ─────────────────────────────────────────────────────────────────────────────

def generate_anchor_coupon(
    matches: list[Match],
    strategy: str = "balanced",
    max_rows: int = 1536,
    min_rows: int = 16,
) -> tuple[dict[int, list[str]], int]:
    """
    Finds the shape that maximises the strategy objective with no budget ceiling.
    Searches all (n_full, n_half) pairs in [min_rows, max_rows] without applying
    the strategy's shape_min_utilisation floor, revealing the model's natural shape.
    """
    cfg    = STRATEGIES.get(strategy, STRATEGIES["balanced"])
    n      = len(matches)
    if cfg.name == "jackpot":
        ranked = sorted(matches, key=lambda m: _jackpot_coverage_key(m, cfg))
    else:
        ranked = sorted(matches, key=lambda m: _composite_score(m, cfg))

    candidates: list[tuple[int, int, int]] = []
    for nf in range(n + 1):
        for nh in range(n - nf + 1):
            rows = (3 ** nf) * (2 ** nh)
            if min_rows <= rows <= max_rows:
                candidates.append((rows, nf, nh))

    if not candidates:
        coupon = _build_coupon(ranked, 0, 0, cfg)
        return coupon, 1

    best_obj  = -1.0
    best_rows = candidates[0][0]
    best_nf   = candidates[0][1]
    best_nh   = candidates[0][2]

    for rows, nf, nh in candidates:
        coupon = _build_coupon(ranked, nf, nh, cfg)
        p_win  = compute_p_win(matches, coupon)

        if cfg.min_p_win_floor > 0.0 and p_win < cfg.min_p_win_floor:
            continue

        pvr = compute_pool_value_ratio(matches, coupon)
        if pvr is None:
            pvr = 1.0

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


def compare_coupons(
    anchor_coupon: dict[int, list[str]],
    budget_coupon: dict[int, list[str]],
    matches: list[Match],
) -> dict:
    """
    Returns per-match coverage changes from anchor to budget coupon.
    Counts how many matches had their coverage level raised or lowered.
    """
    full_to_half   = 0
    full_to_single = 0
    half_to_single = 0
    single_to_half = 0
    single_to_full = 0
    half_to_full   = 0

    for m in matches:
        a = len(anchor_coupon.get(m.number, []))
        b = len(budget_coupon.get(m.number, []))
        if   a == 3 and b == 2: full_to_half   += 1
        elif a == 3 and b == 1: full_to_single += 1
        elif a == 2 and b == 1: half_to_single += 1
        elif a == 1 and b == 2: single_to_half += 1
        elif a == 1 and b == 3: single_to_full += 1
        elif a == 2 and b == 3: half_to_full   += 1

    return {
        "full_to_half":   full_to_half,
        "full_to_single": full_to_single,
        "half_to_single": half_to_single,
        "single_to_half": single_to_half,
        "single_to_full": single_to_full,
        "half_to_full":   half_to_full,
    }
