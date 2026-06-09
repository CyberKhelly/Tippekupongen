"""
Model verification report.

For each fixture in the current week's coupons, prints:
  - Model H/U/B probabilities (same pipeline as Kampanalyse in app.py)
  - Recommended pick, confidence, coverage depth
  - Public tip distribution and pool-value signal (model - public)
  - Reason for the coverage decision

Summary:
  - Singles / Halvdekk / Heldekk counts
  - Singles where the model's recommended pick also has positive pool value
  - Matches where crowd disagreement caused the effective-confidence adjustment

Usage:
    python verify_model.py
    python verify_model.py --budget 96
    python verify_model.py --week 24 --year 2026
"""
from __future__ import annotations
import argparse
from datetime import datetime as _dt


# ─── Coverage reason helper ───────────────────────────────────────────────────

def _reason(m, n_picks: int) -> str:
    conf = m.confidence * 100
    cov_name = {1: "Single", 2: "Halvdekk", 3: "Heldekk"}.get(n_picks, "?")

    if not m.has_public_tips:
        return f"Conf {conf:.0f}% -> {cov_name}"

    vals = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
    rec_val = vals.get(m.recommendation, 0) or 0.0
    cds = m.crowd_disagreement_score or 0.0

    if n_picks == 1:
        if rec_val > 10:
            return f"Conf {conf:.0f}% | pick underplayed {rec_val:+.0f}pp -> strong Single"
        return f"Conf {conf:.0f}%"
    elif n_picks == 2:
        if rec_val < -15:
            return f"Conf {conf:.0f}% | crowd pressure {rec_val:+.0f}pp -> Halvdekk"
        return f"Conf {conf:.0f}% | CDS {cds:.0f}pp"
    else:
        if rec_val < -15:
            return f"Conf {conf:.0f}% (uncertain) | crowd pressure {rec_val:+.0f}pp -> Heldekk"
        return f"Conf {conf:.0f}% (uncertain)"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Model verification report")
    parser.add_argument("--budget", type=float, default=192.0,
                        help="Budget in NOK (default 192)")
    parser.add_argument("--week",   type=int,   default=None)
    parser.add_argument("--year",   type=int,   default=None)
    args = parser.parse_args()

    from db.schema import init_db
    from db.coupon import list_coupons
    from db.enrichment import get_coupon_enrichment
    from models.match import Match
    from analysis.probability import process_match
    from analysis.model import run_model
    from analysis.classifier import classify_match
    from analysis.optimizer import optimize_coupon, _effective_confidence

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

        print(f"\n{'='*110}")
        print(f"  {coupon['label']}  [{coupon_id}]  Budget: {args.budget:.0f} NOK")
        print(f"{'='*110}")

        if not fixtures:
            print("  No fixtures found.")
            continue

        # ── Build matches — exact same pipeline as app.py::load_matches() ─────
        matches: list[Match] = []
        for f in fixtures:
            oh  = f.get("odds_h"); ou = f.get("odds_u"); ob = f.get("odds_b")
            src = f.get("odds_source", "")

            # NT expert tips fallback (mirrors data/loader.py::_best_odds)
            if not (oh and ou and ob):
                ex_h = f.get("expert_h")
                ex_u = f.get("expert_u")
                ex_b = f.get("expert_b")
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

        picks, total_rows = optimize_coupon(matches, args.budget)

        # ── Per-fixture report ────────────────────────────────────────────────
        _cov = {1: "Single", 2: "Halvdekk", 3: "Heldekk"}

        n_single = n_halvdekk = n_heldekk = 0
        n_single_with_value = 0     # Singles where pick also has +pool value
        n_cds_adjusted = 0          # Matches where effective_confidence != confidence

        COL_W = 26  # match name column width
        print()
        hdr = (
            f"{'#':>3}  {'Kamp':<{COL_W}}  "
            f"{'ModH%':>6} {'ModU%':>6} {'ModB%':>6}  "
            f"{'Pick':>4}  {'Konf%':>6}  {'Dekning':<10}  "
            f"{'PubH%':>6} {'PubU%':>6} {'PubB%':>6}  "
            f"{'ValH':>6} {'ValU':>6} {'ValB':>6}  "
            f"Arsak"
        )
        print(hdr)
        print("-" * (len(hdr) + 20))

        for m in matches:
            n   = len(picks[m.number])
            cov = _cov[n]

            mh_s = f"{m.prob_h*100:.1f}"
            mu_s = f"{m.prob_u*100:.1f}"
            mb_s = f"{m.prob_b*100:.1f}"
            cf_s = f"{m.confidence*100:.1f}"

            pub_h_s = f"{m.pub_prob_h*100:.0f}" if m.pub_prob_h is not None else "-"
            pub_u_s = f"{m.pub_prob_u*100:.0f}" if m.pub_prob_u is not None else "-"
            pub_b_s = f"{m.pub_prob_b*100:.0f}" if m.pub_prob_b is not None else "-"

            v_h_s = f"{m.value_h:+.0f}" if m.value_h is not None else "-"
            v_u_s = f"{m.value_u:+.0f}" if m.value_u is not None else "-"
            v_b_s = f"{m.value_b:+.0f}" if m.value_b is not None else "-"

            reason = _reason(m, n)

            eff = _effective_confidence(m)
            if m.has_public_tips and abs(eff - m.confidence) > 1e-9:
                n_cds_adjusted += 1
                cov_display = f"{cov}*"   # asterisk = crowd adjustment active
            else:
                cov_display = cov

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
                f"{m.recommendation:>4}  {cf_s:>6}  {cov_display:<10}  "
                f"{pub_h_s:>6} {pub_u_s:>6} {pub_b_s:>6}  "
                f"{v_h_s:>6} {v_u_s:>6} {v_b_s:>6}  "
                f"{reason}"
            )

        print()
        print(f"Budget {args.budget:.0f} NOK -> {total_rows} rows")
        print(f"  Singles:   {n_single:2d}  "
              f"({n_single_with_value} also have positive pool value on the pick)")
        print(f"  Halvdekk:  {n_halvdekk:2d}")
        print(f"  Heldekk:   {n_heldekk:2d}")
        print(f"  * = effective confidence adjusted by crowd disagreement: {n_cds_adjusted} match(es)")
        print()
        print("Consistency note: model H/U/B above equals what Kampanalyse and")
        print("Statistikk both show (shared pipeline: process_match -> run_model).")


if __name__ == "__main__":
    main()
