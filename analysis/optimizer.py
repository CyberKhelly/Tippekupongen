from models.match import Match


def optimize_coupon(
    matches: list[Match],
    budget_nok: float,
    cost_per_row: float = 1.0,
) -> tuple[dict[int, list[str]], int]:
    """
    Greedy budget-based coupon optimizer.

    The number of coupon rows equals the product of pick counts per match.
    Example: 12 singles = 1 row. Two half-covers + 10 singles = 4 rows.

    Strategy:
      1. Bankers are forced single picks (never covered).
      2. Sort remaining matches by confidence ascending (least certain first).
      3. Pass 1 — upgrade 1-pick → 2-pick (half cover) while rows fit budget.
      4. Pass 2 — upgrade 2-pick → 3-pick (full cover) while rows fit budget.
      5. For each match, the top N picks by probability are selected.

    Returns:
      coupon  — dict of match.number → sorted list of picks e.g. ["H", "U"]
      rows    — total coupon rows after optimization
    """
    max_rows = max(1, int(budget_nok / cost_per_row))

    assignments: dict[int, int] = {m.number: 1 for m in matches}

    def total_rows() -> int:
        result = 1
        for v in assignments.values():
            result *= v
        return result

    # Non-banker candidates sorted by confidence ascending (most uncertain first)
    candidates = sorted(
        [m for m in matches if m.classification != "banker"],
        key=lambda m: m.confidence,
    )

    # Pass 1: upgrade 1-pick → 2-pick
    for m in candidates:
        if total_rows() * 2 <= max_rows:
            assignments[m.number] = 2
        else:
            break  # All upgrades cost ×2, so no point continuing

    # Pass 2: upgrade 2-pick → 3-pick for already half-covered matches
    half_covered = [m for m in candidates if assignments[m.number] == 2]
    for m in half_covered:
        curr = total_rows()
        # Replacing this match's factor of 2 with 3: new total = (curr/2)*3
        new_total = (curr // assignments[m.number]) * 3
        if new_total <= max_rows:
            assignments[m.number] = 3

    # Build final picks: take top N probabilities for each match
    coupon: dict[int, list[str]] = {}
    for m in matches:
        n = assignments[m.number]
        ranked = sorted(
            [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
            key=lambda x: x[1],
            reverse=True,
        )
        coupon[m.number] = sorted(p[0] for p in ranked[:n])

    return coupon, total_rows()
