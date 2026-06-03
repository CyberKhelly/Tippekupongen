from models.match import Match
from analysis.classifier import classification_label

WIDTH = 80


def _sep(char: str = "-") -> None:
    print(char * WIDTH)


def _trunc(text: str, max_len: int) -> str:
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


def print_header() -> None:
    _sep("=")
    print("  TIPPEKUPONGEN ANALYSER  v1.0")
    print("  Probability analysis and coupon optimizer")
    _sep("=")

    print()


def print_analysis_table(matches: list[Match]) -> None:
    print("  MATCH ANALYSIS")
    _sep()

    header = (
        f"  {'#':>2}  "
        f"{'Match':<30}  "
        f"{'H%':>6}  "
        f"{'U%':>6}  "
        f"{'B%':>6}  "
        f"{'Pick':>4}  "
        f"{'Conf':>6}  "
        f"{'Type':<11}"
    )
    print(header)
    _sep()

    for m in matches:
        label = _trunc(m.label, 30)
        cls = classification_label(m.classification)
        marker = " *" if m.classification == "banker" else "  "

        print(
            f"  {m.number:>2}  "
            f"{label:<30}  "
            f"{m.prob_h * 100:5.1f}%  "
            f"{m.prob_u * 100:5.1f}%  "
            f"{m.prob_b * 100:5.1f}%  "
            f"{m.recommendation:>4}  "
            f"{m.confidence * 100:5.1f}%  "
            f"{cls:<11}{marker}"
        )

    _sep()
    print("  Pick = recommended outcome  |  Conf = confidence  |  * = Banker")
    print()


def print_summary(matches: list[Match]) -> None:
    bankers    = [m for m in matches if m.classification == "banker"]
    uncertain  = [m for m in matches if m.classification == "uncertain"]
    full_cover = [m for m in matches if m.classification == "full_cover"]
    half_cover = [m for m in matches if m.classification == "half_cover"]

    print("  SUMMARY")
    _sep()

    if bankers:
        names = "  ".join(f"#{m.number} {m.recommendation}" for m in bankers)
        print(f"  Bankers    : {names}")
    else:
        print("  Bankers    : None identified this week")

    if uncertain:
        names = "  ".join(f"#{m.number}" for m in uncertain)
        print(f"  Uncertain  : {names}")
    else:
        print("  Uncertain  : None")

    if full_cover:
        names = "  ".join(f"#{m.number}" for m in full_cover)
        print(f"  Full Cover : {names}")

    if half_cover:
        names = "  ".join(f"#{m.number}" for m in half_cover)
        print(f"  Half Cover : {names}")

    avg_conf = sum(m.confidence for m in matches) / len(matches)
    print(f"\n  Average confidence : {avg_conf * 100:.1f}%")
    print(f"  Matches analysed   : {len(matches)}")
    _sep()
    print()


def print_coupon(
    matches: list[Match],
    picks: dict[int, list[str]],
    total_rows: int,
    budget: float,
    cost_per_row: float,
) -> None:
    total_cost = total_rows * cost_per_row

    print(
        f"  OPTIMIZED COUPON  |  Budget: {budget:.0f} NOK  "
        f"|  {cost_per_row:.2f} NOK/row"
    )
    _sep()

    header = (
        f"  {'#':>2}  "
        f"{'Match':<30}  "
        f"{'Picks':<9}  "
        f"Coverage"
    )
    print(header)
    _sep()

    for m in matches:
        match_picks = picks[m.number]
        label = _trunc(m.label, 30)
        picks_str = " / ".join(match_picks)

        if len(match_picks) == 3:
            coverage = "Full cover"
        elif len(match_picks) == 2:
            coverage = "Half cover"
        else:
            coverage = "Single"

        if m.classification == "banker":
            coverage += "  [BANKER]"

        print(
            f"  {m.number:>2}  "
            f"{label:<30}  "
            f"{picks_str:<9}  "
            f"{coverage}"
        )

    _sep()
    print(f"  Rows used  : {total_rows}")
    print(f"  Total cost : {total_cost:.2f} NOK  (budget: {budget:.0f} NOK)")

    if total_cost <= budget:
        print(f"  Remaining  : {budget - total_cost:.2f} NOK")
    else:
        print(f"  WARNING    : Over budget by {total_cost - budget:.2f} NOK")

    _sep()
    print()
