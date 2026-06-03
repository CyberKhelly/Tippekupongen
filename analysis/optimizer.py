from models.match import Match


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

    Half covers pick the top-2 outcomes by normalised probability.
    Full covers pick all three.
    """
    max_rows = max(1, int(budget_nok / cost_per_row))
    n = len(matches)

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

    # Assign deepest coverage to least confident matches
    ranked = sorted(matches, key=lambda m: m.confidence)

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
