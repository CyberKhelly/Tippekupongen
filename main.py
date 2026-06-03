"""
Tippekupongen Analyser v1.0

Entry point. Prompts for match data, runs probability analysis,
classifies matches, then optimizes a coupon within a given budget.
"""

import sys

from models.match import Match
from analysis.probability import process_match
from analysis.classifier import classify_match
from analysis.optimizer import optimize_coupon
from ui.display import (
    print_header,
    print_analysis_table,
    print_summary,
    print_coupon,
)

NUM_MATCHES = 12  # Change to 13 for weeks with 13 matches


def _get_float(prompt: str, min_val: float = 1.01) -> float:
    """Prompt until the user enters a valid decimal number >= min_val."""
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
            if value < min_val:
                print(f"    Must be at least {min_val}. Try again.")
                continue
            return value
        except ValueError:
            print("    Invalid input — enter a decimal number, e.g. 2.50")


def input_matches() -> list[Match]:
    print("  Enter details for each match.")
    print("  Odds must be decimal format (e.g. 2.50, not 3/2 or +150).")
    print("  Press Enter without a name to use a placeholder.")
    print()

    matches: list[Match] = []

    for i in range(1, NUM_MATCHES + 1):
        print(f"  -- Match {i}/{NUM_MATCHES} " + "-" * 40)
        home = input("    Home team : ").strip() or f"Home {i}"
        away = input("    Away team : ").strip() or f"Away {i}"
        print(f"    Odds for {home} vs {away}:")
        odds_h = _get_float("      H (home win) : ")
        odds_u = _get_float("      U (draw)     : ")
        odds_b = _get_float("      B (away win) : ")

        match = Match(
            number=i,
            home_team=home,
            away_team=away,
            odds_h=odds_h,
            odds_u=odds_u,
            odds_b=odds_b,
        )
        process_match(match)
        classify_match(match)
        matches.append(match)
        print()

    return matches


def input_budget() -> tuple[float, float]:
    print("  COUPON OPTIMIZER SETTINGS")
    print("  " + "─" * 40)

    while True:
        raw = input("  Budget in NOK (e.g. 192): ").strip()
        try:
            budget = float(raw)
            if budget <= 0:
                print("  Budget must be greater than 0.")
                continue
            break
        except ValueError:
            print("  Invalid input.")

    raw = input("  Cost per row in NOK [default 1.0]: ").strip()
    try:
        cost = float(raw) if raw else 1.0
        cost = cost if cost > 0 else 1.0
    except ValueError:
        cost = 1.0

    return budget, cost


def main() -> None:
    print_header()

    try:
        matches = input_matches()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
        sys.exit(0)

    print_analysis_table(matches)
    print_summary(matches)

    try:
        budget, cost_per_row = input_budget()
    except KeyboardInterrupt:
        print("\n\n  Cancelled.")
        sys.exit(0)

    picks, total_rows = optimize_coupon(matches, budget, cost_per_row)
    print()
    print_coupon(matches, picks, total_rows, budget, cost_per_row)


if __name__ == "__main__":
    main()
