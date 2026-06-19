"""
Model verification report — Phase 6B.

For each fixture in the current week's coupons, prints:
  - Model H/U/B probabilities (same pipeline as Kampanalyse in app.py)
  - Recommended pick, confidence, coverage depth
  - Public tip distribution and pool-value signal (model - public)
  - Value index (model_prob / public_prob) for the recommended pick
  - Whether the halvdekk second pick is contrarian (differs from pure-prob #2)
  - Reason for the coverage decision

Summary per coupon:
  - Singles / Halvdekk / Heldekk counts
  - Contrarian halvdekk picks
  - Effective-confidence adjusted matches (crowd signal active)
  - P(12/12) — exact win probability for the generated system
  - Pool Value Ratio (payout multiplier vs average public ticket)
  - Payout distribution (if --omsetning is provided)

Usage:
    python verify_model.py
    python verify_model.py --strategy jackpot
    python verify_model.py --budget 96 --strategy balanced
    python verify_model.py --week 24 --year 2026 --omsetning 15000000
"""
from __future__ import annotations
import argparse
from datetime import datetime as _dt


# ─── Coverage reason helper ───────────────────────────────────────────────────

def _reason(m, n_picks: int, strategy: str) -> str:
    conf     = m.confidence * 100
    cov_name = {1: "Single", 2: "Halvdekk", 3: "Heldekk"}.get(n_picks, "?")

    if not m.has_public_tips:
        return f"Conf {conf:.0f}% [{strategy}] -> {cov_name}"

    vals    = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
    rec_val = vals.get(m.recommendation, 0) or 0.0
    cds     = m.crowd_disagreement_score or 0.0

    if n_picks == 1:
        if rec_val > 10:
            return f"Conf {conf:.0f}% | pick underplayed {rec_val:+.0f}pp -> strong Single [{strategy}]"
        return f"Conf {conf:.0f}% [{strategy}]"
    elif n_picks == 2:
        if rec_val < -15:
            return f"Conf {conf:.0f}% | crowd pressure {rec_val:+.0f}pp -> Halvdekk [{strategy}]"
        return f"Conf {conf:.0f}% | CDS {cds:.0f}pp [{strategy}]"
    else:
        if rec_val < -15:
            return f"Conf {conf:.0f}% (uncertain) | crowd pressure {rec_val:+.0f}pp -> Heldekk [{strategy}]"
        return f"Conf {conf:.0f}% (uncertain) [{strategy}]"


# ─── Halvdekk contrarian detector ─────────────────────────────────────────────

def _is_contrarian(m, picks: list[str]) -> tuple[bool, str]:
    """Returns (is_contrarian, description) for a halvdekk pick."""
    if len(picks) != 2:
        return False, ""
    probs = sorted(
        [("H", m.prob_h), ("U", m.prob_u), ("B", m.prob_b)],
        key=lambda x: x[1], reverse=True,
    )
    top_out = probs[0][0]
    sec_out = probs[1][0]
    expected = sorted([top_out, sec_out])
    if sorted(picks) == expected:
        return False, ""
    prob_map = {o: p for o, p in probs}
    # Jackpot may exclude the top outcome entirely (best-PVR pair logic)
    if top_out not in picks:
        p0 = prob_map.get(picks[0], 0)
        p1 = prob_map.get(picks[1], 0)
        top_p = prob_map.get(top_out, 0)
        return True, (f"excl. top {top_out} ({top_p*100:.0f}%) — picks "
                      f"{picks[0]}({p0*100:.0f}%)+{picks[1]}({p1*100:.0f}%)")
    # Standard case: top included but second pick differs from #2 by probability
    actual_second = [p for p in picks if p != top_out][0]
    prob_sec = prob_map.get(sec_out, 0)
    prob_act = prob_map.get(actual_second, 0)
    return True, f"contrarian: {actual_second} ({prob_act*100:.0f}%) over {sec_out} ({prob_sec*100:.0f}%)"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Model verification report — Phase 6B")
    parser.add_argument("--budget",    type=float, default=192.0,
                        help="Budget in NOK (default 192)")
    parser.add_argument("--strategy",  type=str,   default="balanced",
                        choices=["safe", "balanced", "jackpot"],
                        help="Strategy mode (default balanced)")
    parser.add_argument("--week",      type=int,   default=None)
    parser.add_argument("--year",      type=int,   default=None)
    parser.add_argument("--omsetning", type=float, default=None,
                        help="NT turnover in NOK for payout simulation (optional)")
    args = parser.parse_args()

    from db.schema import init_db
    from db.coupon import list_coupons
    from db.enrichment import get_coupon_enrichment
    from models.match import Match
    from analysis.probability import process_match
    from analysis.model import run_model
    from analysis.classifier import classify_match
    from analysis.optimizer import optimize_coupon, _effective_confidence
    from analysis.pool_value import (
        compute_value_index, compute_p_win,
        compute_pool_value_ratio, simulate_payout,
    )

    init_db()

    iso  = _dt.now().isocalendar()
    week = args.week or iso.week
    year = args.year or iso.year

    coupons_meta = list_coupons(week=week, year=year)
    if not coupons_meta:
        print(f"No coupons in DB for week {week}/{year}.")
        print("Run: python sync.py --refresh-coupons")
        return

    for coupon in coupons_meta:
        coupon_id = coupon["coupon_id"]
        fixtures  = get_coupon_enrichment(coupon_id)

        print(f"\n{'='*120}")
        print(f"  {coupon['label']}  [{coupon_id}]  Budget: {args.budget:.0f} NOK  Strategy: {args.strategy.upper()}")
        print(f"{'='*120}")

        if not fixtures:
            print("  No fixtures found.")
            continue

        # ── Build matches — exact same pipeline as app.py::load_matches() ─────
        matches: list[Match] = []
        for f in fixtures:
            oh  = f.get("odds_h"); ou = f.get("odds_u"); ob = f.get("odds_b")
            src = f.get("odds_source", "")

            if not (oh and ou and ob):
                ex_h = f.get("expert_h"); ex_u = f.get("expert_u"); ex_b = f.get("expert_b")
                if (ex_h and ex_u and ex_b
                        and float(ex_h) > 0 and float(ex_u) > 0 and float(ex_b) > 0):
                    oh  = round(100.0 / float(ex_h), 4)
                    ou  = round(100.0 / float(ex_u), 4)
                    ob  = round(100.0 / float(ex_b), 4)
                    src = "nt_expert"
                else:
                    oh = ou = ob = 3.0
                    src = "placeholder"

            m = Match(
                number=f["match_number"],
                home_team=f.get("home_name", ""),
                away_team=f.get("away_name", ""),
                odds_h=float(oh), odds_u=float(ou), odds_b=float(ob),
                odds_source=src,
            )
            process_match(m)
            run_model(m, f)
            classify_match(m)
            matches.append(m)

        picks, total_rows = optimize_coupon(matches, args.budget, strategy=args.strategy)

        # ── Per-fixture report ────────────────────────────────────────────────
        _cov   = {1: "Single", 2: "Halvdekk", 3: "Heldekk"}
        COL_W  = 26

        n_single = n_halvdekk = n_heldekk = 0
        n_single_with_value  = 0
        n_cds_adjusted       = 0
        n_contrarian         = 0

        print()
        hdr = (
            f"{'#':>3}  {'Kamp':<{COL_W}}  "
            f"{'ModH%':>6} {'ModU%':>6} {'ModB%':>6}  "
            f"{'Pick':>4}  {'Konf%':>6}  {'Dekning':<12}  "
            f"{'PubH%':>6} {'PubU%':>6} {'PubB%':>6}  "
            f"{'ValH':>6} {'ValU':>6} {'ValB':>6}  "
            f"{'VI':>5}  "
            f"Arsak"
        )
        print(hdr)
        print("-" * (len(hdr) + 10))

        for m in matches:
            n        = len(picks[m.number])
            cov      = _cov[n]
            mh_s     = f"{m.prob_h*100:.1f}"
            mu_s     = f"{m.prob_u*100:.1f}"
            mb_s     = f"{m.prob_b*100:.1f}"
            cf_s     = f"{m.confidence*100:.1f}"

            pub_h_s  = f"{m.pub_prob_h*100:.0f}" if m.pub_prob_h is not None else "-"
            pub_u_s  = f"{m.pub_prob_u*100:.0f}" if m.pub_prob_u is not None else "-"
            pub_b_s  = f"{m.pub_prob_b*100:.0f}" if m.pub_prob_b is not None else "-"

            v_h_s    = f"{m.value_h:+.0f}" if m.value_h is not None else "-"
            v_u_s    = f"{m.value_u:+.0f}" if m.value_u is not None else "-"
            v_b_s    = f"{m.value_b:+.0f}" if m.value_b is not None else "-"

            # Value index for the recommended pick
            _prob = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(m.recommendation)
            _pub  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(m.recommendation)
            vi    = compute_value_index(_prob or 0, _pub)
            vi_s  = f"{vi:.2f}x" if vi is not None else "  -  "

            reason = _reason(m, n, args.strategy)

            # Effective confidence adjustment marker
            eff = _effective_confidence(m)
            cds_mark = "*" if (m.has_public_tips and abs(eff - m.confidence) > 1e-9) else " "
            if cds_mark == "*":
                n_cds_adjusted += 1

            # Contrarian halvdekk pick marker
            is_con, con_desc = _is_contrarian(m, picks[m.number])
            con_mark = "C" if is_con else " "
            if is_con:
                n_contrarian += 1
                reason += f"  [{con_desc}]"

            cov_display = f"{cov}{cds_mark}{con_mark}"

            if n == 1:
                n_single += 1
                if m.value_h is not None:
                    rv = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(m.recommendation, 0) or 0
                    if rv > 0:
                        n_single_with_value += 1
            elif n == 2:
                n_halvdekk += 1
            else:
                n_heldekk += 1

            name = (m.home_team[:11] + "-" + m.away_team[:11])[:COL_W]
            print(
                f"{m.number:>3}  {name:<{COL_W}}  "
                f"{mh_s:>6} {mu_s:>6} {mb_s:>6}  "
                f"{m.recommendation:>4}  {cf_s:>6}  {cov_display:<12}  "
                f"{pub_h_s:>6} {pub_u_s:>6} {pub_b_s:>6}  "
                f"{v_h_s:>6} {v_u_s:>6} {v_b_s:>6}  "
                f"{vi_s:>5}  "
                f"{reason}"
            )

        # ── Coupon-level analytics ─────────────────────────────────────────────
        p_win    = compute_p_win(matches, picks)
        pv_ratio = compute_pool_value_ratio(matches, picks)

        print()
        print(f"Budget {args.budget:.0f} NOK -> {total_rows} rows  |  Strategy: {args.strategy.upper()}")
        print(f"  Singles:    {n_single:2d}  "
              f"({n_single_with_value} also have positive pool value on the pick)")
        print(f"  Halvdekk:   {n_halvdekk:2d}  ({n_contrarian} contrarian second pick(s))")
        print(f"  Heldekk:    {n_heldekk:2d}")
        print(f"  * = effective confidence adjusted by crowd (balanced threshold): {n_cds_adjusted} match(es)")
        print(f"  C = contrarian halvdekk (strategy-preferred second pick differs from #2 by prob)")
        print()
        print(f"  P(12/12 exact win):    {p_win*100:.3f}%  (1 in {round(1/p_win):,})" if p_win > 0 else "  P(12/12): 0%")
        if pv_ratio is not None:
            pv_sign = "+" if pv_ratio >= 1.0 else ""
            pv_desc = "positive pool edge" if pv_ratio >= 1.0 else "crowd pressure (negative edge)"
            print(f"  Pool Value Ratio:      {pv_ratio:.3f}×  ({pv_desc})")
        else:
            print(f"  Pool Value Ratio:      — (insufficient public data)")

        # ── Payout simulation ─────────────────────────────────────────────────
        if args.omsetning and args.omsetning > 0:
            print()
            print(f"  Payout simulation  (omsetning={args.omsetning:,.0f} NOK, prize_rate=52%, n_sims=50 000):")
            sim = simulate_payout(
                matches, picks, total_rows, args.omsetning, n_sims=50_000
            )
            if sim.get("n_winning_sims", 0) == 0:
                print("    No winning draws observed — coupon win probability too low for simulation at 50k draws.")
            else:
                pw_sim = sim["p_win_simulated"]
                print(f"    Simulated P(win):  {pw_sim*100:.3f}%  ({sim['n_winning_sims']:,} of 50 000 draws won)")
                print(f"    Min payout:        {sim['min']:>10,.0f} NOK")
                print(f"    P10 payout:        {sim['p10']:>10,.0f} NOK")
                print(f"    Median payout:     {sim['median']:>10,.0f} NOK")
                print(f"    P90 payout:        {sim['p90']:>10,.0f} NOK")
                print(f"    Max payout:        {sim['max']:>10,.0f} NOK")
                print(f"    Mean payout:       {sim['mean']:>10,.0f} NOK")
                print(f"    Avg winners/draw:  {sim['e_winners']:>10,d} rekker deler potten ved gevinst")
                print(f"    {sim['narrative']}")
                print(f"    * Estimates only — actual NT payout depends on real turnover, prize tier, and winner count.")
        else:
            print(f"\n  Payout simulation: provide --omsetning <NOK> for estimates.")

        print()
        print("  Consistency note: model H/U/B above equals what Kampanalyse and")
        print("  Statistikk both show (shared pipeline: process_match -> run_model).")
        print("  Strategy only affects coverage ranking and halvdekk second picks.")


if __name__ == "__main__":
    main()
