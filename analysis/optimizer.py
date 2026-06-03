from functools import reduce
from operator import mul
from models.match import Match


def optimize_coupon(
    matches: list[Match],
    budget_nok: float,
    cost_per_row: float = 1.0,
) -> tuple[dict[int, list[str]], int]:
    """
    Greedy Tippekupongen optimizer.

    Rows = product of pick counts across all 12 matches.
    A single on every match = 1 row.
    One half cover on top = 2 rows.
    One full cover on top = 3 rows. Etc.

    Algorithm
    ---------
    1. Start: all matches are singles (1 row total).
    2. Sort matches by confidence ascending — most uncertain first.
    3. For each match in that order:
         - Try to upgrade it by one level (1→2, or 2→3).
         - If the new row count stays within max_rows, apply the upgrade.
         - Keep upgrading the same match until it reaches 3 picks or
           the next upgrade would exceed the budget.
         - Then move to the next match.
    4. The most uncertain matches therefore get the deepest coverage first.
       High-confidence matches are processed last and likely stay as singles.

    Pick selection
    --------------
    A match assigned N picks receives the top-N outcomes ranked by
    normalized probability:
      - 1 pick  → highest-probability outcome (e.g. H)
      - 2 picks → top two outcomes (e.g. H/U or H/B depending on probs)
      - 3 picks → all three (H/U/B)
    """
    max_rows = max(1, int(budget_nok / cost_per_row))
    assignments: dict[int, int] = {m.number: 1 for m in matches}

    def total_rows() -> int:
        return reduce(mul, assignments.values(), 1)

    for m in sorted(matches, key=lambda m: m.confidence):
        while assignments[m.number] < 3:
            curr = total_rows()
            lvl  = assignments[m.number]
            # Cost of upgrading: 1→2 doubles rows; 2→3 multiplies by 1.5
            new_rows = (curr * 2) if lvl == 1 else (curr // 2) * 3
            if new_rows <= max_rows:
                assignments[m.number] += 1
            else:
                break  # this match is as upgraded as the budget allows

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
