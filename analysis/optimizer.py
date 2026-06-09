from models.match import Match


def _effective_confidence(m: Match) -> float:
    """
    Confidence adjusted for crowd value signals (Phase 5).

    If the crowd strongly underplays the model's top pick (positive value on
    that outcome), effective confidence is raised slightly → less coverage
    needed.  The crowd is on our side from a pool-value perspective.

    If the crowd strongly overplays the model's top pick (negative value →
    herd risk), effective confidence is lowered slightly → more coverage,
    since being wrong here costs more relative to the pool payout.

    Adjustment is capped at ±2pp so it only tips borderline decisions and
    never overrides the model's probability signal.
    """
    conf = m.confidence
    if not m.has_public_tips:
        return conf

    vals      = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
    top_value = vals.get(m.recommendation)
    if top_value is None:
        return conf

    if top_value > 10.0:      # crowd underplaying our pick by > 10pp
        return min(conf + 0.02, 1.0)
    if top_value < -15.0:     # crowd overplaying our pick by > 15pp
        return max(conf - 0.02, 0.0)
    return conf


def optimize_coupon(
    matches: list[Match],
    budget_nok: float,
    cost_per_row: float = 1.0,
) -> tuple[dict[int, list[str]], int]:
    """
    Optimal Tippekupongen coupon optimizer.

    Finds the (n_full_covers, n_half_covers) pair that maximises
    rows used without exceeding the budget, then assigns deepest
    coverage to the least confident matches.

        rows = 3^n_full * 2^n_half  <=  max_rows

    Because every combination is checked exhaustively (at most 13×13
    pairs for 12 matches), the result is provably optimal for all
    budget values — including the four presets 32/96/192/384 NOK,
    which all achieve exact full-budget coverage:

        32  NOK → 0 full covers + 5 half covers = 32 rows
        96  NOK → 1 full cover  + 5 half covers = 96 rows
       192  NOK → 1 full cover  + 6 half covers = 192 rows
       384  NOK → 1 full cover  + 7 half covers = 384 rows

    Phase 5: coverage ranking uses _effective_confidence() which nudges
    borderline matches based on crowd value signals (±2pp cap).
    Half covers pick the top-2 outcomes by model probability.
    Full covers pick all three.
    """
    max_rows = max(1, int(budget_nok / cost_per_row))
    n        = len(matches)

    best_rows = 1
    best_nf   = 0   # n_full_covers
    best_nh   = 0   # n_half_covers

    for nf in range(n + 1):
        for nh in range(n - nf + 1):
            rows = (3 ** nf) * (2 ** nh)
            if rows <= max_rows and rows > best_rows:
                best_rows = rows
                best_nf   = nf
                best_nh   = nh

    # Assign deepest coverage to least confident matches (Phase 5: crowd-adjusted)
    ranked = sorted(matches, key=_effective_confidence)

    assignments: dict[int, int] = {}
    for i, m in enumerate(ranked):
        if i < best_nf:
            assignments[m.number] = 3          # full cover
        elif i < best_nf + best_nh:
            assignments[m.number] = 2          # half cover
        else:
            assignments[m.number] = 1          # single

    coupon: dict[int, list[str]] = {}
    for m in matches:
        k = assignments[m.number]
        ranked_probs = sorted(
            [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
            key=lambda x: x[1],
            reverse=True,
        )
        coupon[m.number] = sorted(p[0] for p in ranked_probs[:k])

    return coupon, best_rows
