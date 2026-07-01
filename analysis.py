"""
analysis.py — Evidensbasert analysepipeline for TippeIQ.

Leser evaluerte kupongsnapshots (Phase 15) og produserer:
  1. Calibration Report   — er modellens sannsynligheter kalibrerte?
  2. Model vs Public      — er modellen skarpere enn folket?
  3. Coverage Audit       — fungerer single/halvdekk/heldekk?
  4. Strategy Performance — balanced vs jackpot vs safe over tid
  5. PVR Audit            — korrelerer PVR med faktisk dekning?

Kjøres etter: python evaluate.py --week XX --year YYYY --fetch

Bruk:
  python analysis.py                        # alle rapporter
  python analysis.py --report calibration   # én rapport
  python analysis.py --week 27 --year 2026  # filtrer på uke/år
  python analysis.py --strategy balanced    # filtrer på strategi
  python analysis.py --min-n 5             # min picks per bøtte (default: 3)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from db.connection import get_conn


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def load_picks(
    week: int | None = None,
    year: int | None = None,
    strategy: str | None = None,
) -> list[dict]:
    """
    Return all saved-coupon picks joined with results and snapshot metadata.
    Adds computed fields: has_result, covered, pick_correct.
    """
    clauses: list[str] = []
    params:  list[Any] = []
    if week     is not None: clauses.append("sc.week = ?");     params.append(week)
    if year     is not None: clauses.append("sc.year = ?");     params.append(year)
    if strategy is not None: clauses.append("sc.strategy = ?"); params.append(strategy)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    with get_conn() as conn:
        rows = conn.execute(f"""
            SELECT
                sp.pick_id, sp.snapshot_id, sp.fixture_id,
                sp.match_number, sp.home_team, sp.away_team,
                sp.pick, sp.coverage_type, sp.selected_outcomes,
                sp.model_prob_h, sp.model_prob_u, sp.model_prob_b,
                sp.public_prob_h, sp.public_prob_u, sp.public_prob_b,
                sp.picked_prob, sp.conviction, sp.cds, sp.vi,
                sp.value_h, sp.value_u, sp.value_b,
                sc.strategy, sc.budget_nok, sc.pvr, sc.p_win,
                sc.week, sc.year, sc.coupon_id,
                mr.result_1x2
            FROM saved_coupon_picks sp
            JOIN  saved_coupons  sc ON sc.snapshot_id = sp.snapshot_id
            LEFT JOIN match_results mr ON mr.fixture_id = sp.fixture_id
            {where}
            ORDER BY sc.year, sc.week, sc.strategy, sp.match_number
        """, params).fetchall()

    picks = []
    for r in rows:
        p = dict(r)
        so = p.get("selected_outcomes")
        try:
            p["selected_outcomes"] = json.loads(so) if isinstance(so, str) else (so or [p["pick"]])
        except Exception:
            p["selected_outcomes"] = [p["pick"]]

        result           = p.get("result_1x2")
        p["has_result"]  = result is not None
        p["covered"]     = (result in p["selected_outcomes"]) if result else None
        p["pick_correct"]= (result == p["pick"])              if result else None
        picks.append(p)

    return picks


def _build_snapshots(picks: list[dict]) -> list[dict]:
    """Aggregate picks into snapshot-level summaries."""
    by_snap: dict[str, list[dict]] = defaultdict(list)
    for p in picks:
        by_snap[p["snapshot_id"]].append(p)

    snapshots = []
    for sid, sp_list in by_snap.items():
        first     = sp_list[0]
        evaluated = [p for p in sp_list if p["has_result"]]
        n_cov     = sum(1 for p in evaluated if p["covered"])
        n_cor     = sum(1 for p in evaluated if p["pick_correct"])
        snapshots.append({
            "snapshot_id":   sid,
            "coupon_id":     first["coupon_id"],
            "strategy":      first["strategy"],
            "budget_nok":    first["budget_nok"],
            "pvr":           first["pvr"],
            "p_win":         first["p_win"],
            "week":          first["week"],
            "year":          first["year"],
            "n_picks":       len(sp_list),
            "n_evaluated":   len(evaluated),
            "n_covered":     n_cov,
            "n_correct":     n_cor,
            "coverage_rate": n_cov / len(evaluated) if evaluated else None,
            "exact_rate":    n_cor / len(evaluated) if evaluated else None,
        })
    return snapshots


# ══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
# ══════════════════════════════════════════════════════════════════════════════

_W = 72  # terminal width

def _section(title: str) -> None:
    print()
    print("=" * _W)
    print(f"  {title}")
    print("=" * _W)

def _hr() -> None:
    print("-" * _W)

def _pct(n: float | None, d: float | None, decimals: int = 1) -> str:
    if n is None or not d:
        return "  -  "
    return f"{100 * n / d:>{4 + decimals}.{decimals}f}%"

def _bar(ratio: float | None, width: int = 14) -> str:
    if ratio is None or ratio < 0:
        return " " * width
    filled = min(width, round(ratio * width))
    return "#" * filled + "." * (width - filled)

def _tbl(headers: list[str], rows: list[list], widths: list[int]) -> None:
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))

def _no_data(msg: str = "Ingen evaluerte picks enda.") -> None:
    print(f"  [!] {msg}")


# ══════════════════════════════════════════════════════════════════════════════
# 1. Calibration Report
# ══════════════════════════════════════════════════════════════════════════════

_CAL_BUCKETS = [
    (0.00, 0.40, "< 40%    "),
    (0.40, 0.50, "40-50%   "),
    (0.50, 0.60, "50-60%   "),
    (0.60, 0.70, "60-70%   "),
    (0.70, 0.80, "70-80%   "),
    (0.80, 1.01, ">= 80%   "),
]

def report_calibration(picks: list[dict], min_n: int = 3) -> None:
    _section("1. CALIBRATION REPORT")
    print("  Naar modellen sa X%, vant valget faktisk X% av gangene?")
    print()

    evaluated = [
        p for p in picks
        if p["has_result"] and p.get("picked_prob") is not None and p["pick_correct"] is not None
    ]
    if not evaluated:
        _no_data(); return

    # Public's probability for the same pick (for comparison)
    pub_map = {"H": "public_prob_h", "U": "public_prob_u", "B": "public_prob_b"}

    buckets: dict[str, list] = {lbl: [] for *_, lbl in _CAL_BUCKETS}
    for p in evaluated:
        prob = p["picked_prob"]
        for lo, hi, lbl in _CAL_BUCKETS:
            if lo <= prob < hi:
                buckets[lbl].append(p)
                break

    # Brier scores
    model_bs  = sum((p["picked_prob"] - int(p["pick_correct"])) ** 2 for p in evaluated) / len(evaluated)
    pub_bs_vals = [
        (p[pub_map[p["pick"]]] - int(p["pick_correct"])) ** 2
        for p in evaluated
        if p.get(pub_map.get(p["pick"], "")) is not None
    ]
    pub_bs = sum(pub_bs_vals) / len(pub_bs_vals) if pub_bs_vals else None

    headers = ["Botte     ", "  N", "Mod-prob", "Faktisk%", "Avvik(pp)", "Bar              "]
    rows = []
    for *_, lbl in _CAL_BUCKETS:
        ps = buckets[lbl]
        if not ps:
            continue
        avg_prob = sum(p["picked_prob"] for p in ps) / len(ps)
        actual   = sum(1 for p in ps if p["pick_correct"]) / len(ps)
        err_pp   = (avg_prob - actual) * 100
        n_str    = str(len(ps)) if len(ps) >= min_n else f"({len(ps)})"
        if len(ps) >= min_n:
            err_str = f"{err_pp:+.1f}pp"
            bar     = f"M:{_bar(avg_prob,7)} F:{_bar(actual,7)}"
        else:
            err_str = "  -  "
            bar     = "(for faa)"
        rows.append([lbl, n_str, f"{avg_prob:.1%}", f"{actual:.1%}" if len(ps) >= min_n else "-", err_str, bar])

    _tbl(headers, rows, [10, 4, 9, 9, 10, 20])
    print()
    print(f"  Brier Score modell: {model_bs:.4f}", end="")
    if pub_bs is not None:
        diff = model_bs - pub_bs
        winner = "modellen" if diff < -0.001 else ("folket" if diff > 0.001 else "likt")
        print(f"  |  Brier Score folket: {pub_bs:.4f}  ->  Skarpest: {winner}")
    else:
        print()
    print(f"  (Lavere Brier = bedre. Perfekt = 0.0, tilfeldig ~0.25)")
    print(f"  Evaluerte: {len(evaluated)} / {len(picks)}")
    if len(evaluated) < 30:
        print("  [!] Under 30 evaluerte picks -- statistikken er tidlig.")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Model vs Public Report
# ══════════════════════════════════════════════════════════════════════════════

def report_model_vs_public(picks: list[dict], min_n: int = 3) -> None:
    _section("2. MODEL VS PUBLIC")
    print("  Hvem peaker naermest faktisk utfall -- modellen eller folket?")
    print()

    def argmax(ph, pu, pb) -> str | None:
        if None in (ph, pu, pb):
            return None
        return max([("H", ph), ("U", pu), ("B", pb)], key=lambda x: x[1])[0]

    evaluated = []
    for p in picks:
        if not p["has_result"]:
            continue
        mpick = argmax(p.get("model_prob_h"), p.get("model_prob_u"), p.get("model_prob_b"))
        ppick = argmax(p.get("public_prob_h"), p.get("public_prob_u"), p.get("public_prob_b"))
        if mpick is None or ppick is None:
            continue
        result = p["result_1x2"]
        evaluated.append({**p,
            "mpick": mpick, "ppick": ppick,
            "mright": mpick == result, "pright": ppick == result,
            "agree":  mpick == ppick,
        })

    if not evaluated:
        _no_data("Ingen picks med bade modell- og folkeprosenter tilgjengelig."); return

    n          = len(evaluated)
    m_right    = sum(1 for p in evaluated if p["mright"])
    p_right    = sum(1 for p in evaluated if p["pright"])
    both_right = sum(1 for p in evaluated if p["mright"] and p["pright"])
    m_only     = sum(1 for p in evaluated if p["mright"] and not p["pright"])
    p_only     = sum(1 for p in evaluated if not p["mright"] and p["pright"])
    both_wrong = sum(1 for p in evaluated if not p["mright"] and not p["pright"])
    n_agree    = sum(1 for p in evaluated if p["agree"])

    print(f"  Totalt evaluert:    {n}")
    print(f"  Modell riktig:      {m_right}/{n} = {m_right/n:.1%}")
    print(f"  Folket riktig:      {p_right}/{n} = {p_right/n:.1%}")
    print()
    lw = 22
    print(f"  Begge riktig:       {both_right:>4}  {_bar(both_right/n, lw)}")
    print(f"  Kun modell riktig:  {m_only:>4}  {_bar(m_only/n, lw)}  <- modellens unike verdi")
    print(f"  Kun folket riktig:  {p_only:>4}  {_bar(p_only/n, lw)}  <- folkets fordel")
    print(f"  Begge feil:         {both_wrong:>4}  {_bar(both_wrong/n, lw)}")
    print()
    print(f"  Enig med folket: {n_agree}/{n} = {n_agree/n:.1%}")
    print()

    # CDS breakdown
    print("  -- Noyaktighet etter CDS (crowd disagreement score) -----------")
    cds_bands = [
        (0,   3,   "Lav      (0-3)"),
        (3,   7,   "Middels  (3-7)"),
        (7,   15,  "Hoy      (7-15)"),
        (15, 999,  "Svaert hoy (>15)"),
    ]
    headers = ["CDS-niva        ", "  N", "Modell%", "Folket%", "Vinner"]
    rows = []
    for lo, hi, lbl in cds_bands:
        sub = [p for p in evaluated if p.get("cds") is not None and lo <= p["cds"] < hi]
        if len(sub) < min_n:
            continue
        mr = sum(1 for p in sub if p["mright"]) / len(sub)
        pr = sum(1 for p in sub if p["pright"]) / len(sub)
        winner = "Modellen" if mr > pr + 0.03 else ("Folket" if pr > mr + 0.03 else "Likt")
        rows.append([lbl, str(len(sub)), f"{mr:.1%}", f"{pr:.1%}", winner])
    if rows:
        _tbl(headers, rows, [17, 4, 8, 8, 10])
    else:
        print("  (For faa picks per CDS-boette -- trenger mer data)")

    # VI breakdown: high VI should mean model is more confident and right
    print()
    print("  -- Noyaktighet etter VI (value index for valgt tegn) ----------")
    vi_bands = [
        (0.0, 0.8,  "Lav VI   (<0.8)"),
        (0.8, 1.0,  "Under 1  (0.8-1.0)"),
        (1.0, 1.2,  "Over 1   (1.0-1.2)"),
        (1.2, 99.0, "Hoy VI   (>1.2)"),
    ]
    vi_rows = []
    for lo, hi, lbl in vi_bands:
        sub = [p for p in evaluated if p.get("vi") is not None and lo <= p["vi"] < hi]
        if len(sub) < min_n:
            continue
        mr = sum(1 for p in sub if p["mright"]) / len(sub)
        pr = sum(1 for p in sub if p["pright"]) / len(sub)
        vi_rows.append([lbl, str(len(sub)), f"{mr:.1%}", f"{pr:.1%}"])
    if vi_rows:
        _tbl(["VI-niva         ", "  N", "Modell%", "Folket%"], vi_rows, [17, 4, 8, 8])
    else:
        print("  (For faa data)")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Coverage Audit
# ══════════════════════════════════════════════════════════════════════════════

def report_coverage_audit(picks: list[dict]) -> None:
    _section("3. COVERAGE AUDIT")
    print("  Fungerer single/halvdekk/heldekk-strategien i praksis?")
    print()

    evaluated = [p for p in picks if p["has_result"] and p["covered"] is not None]
    if not evaluated:
        _no_data(); return

    # Per coverage type
    print("  -- Dekning per dekningstype ------------------------------------")
    cov_types = ["single", "half_cover", "full_cover"]
    headers = ["Dekningstype", "  N", "Dekket%", "Eksakt%", "Halvd-redning"]
    rows = []
    for ct in cov_types:
        sub = [p for p in evaluated if p["coverage_type"] == ct]
        if not sub:
            continue
        n_cov = sum(1 for p in sub if p["covered"])
        n_cor = sum(1 for p in sub if p["pick_correct"])
        if ct == "half_cover":
            rescued   = sum(1 for p in sub if p["covered"] and not p["pick_correct"])
            rescue_str = f"{rescued}/{len(sub)} = {rescued/len(sub):.1%}"
        else:
            rescue_str = "  -  "
        rows.append([
            ct, str(len(sub)),
            f"{n_cov/len(sub):.1%}",
            f"{n_cor/len(sub):.1%}",
            rescue_str,
        ])
    _tbl(headers, rows, [14, 4, 8, 8, 18])
    print()

    # Halvdekk: which secondary marks cover?
    halvdekk = [p for p in evaluated if p["coverage_type"] == "half_cover"]
    if halvdekk:
        print("  -- Halvdekk: sekundaervalg-analyse ----------------------------")
        combos: dict[str, dict] = defaultdict(lambda: {"n": 0, "cov": 0, "cor": 0})
        for p in halvdekk:
            sec = next((s for s in p["selected_outcomes"] if s != p["pick"]), None)
            key = f"{p['pick']}+{sec}" if sec else p["pick"]
            combos[key]["n"]   += 1
            combos[key]["cov"] += int(bool(p["covered"]))
            combos[key]["cor"] += int(bool(p["pick_correct"]))

        headers2 = ["Kombinasjon", "  N", "Dekket%", "Eksakt%"]
        rows2 = []
        for key, v in sorted(combos.items(), key=lambda x: -x[1]["n"]):
            rows2.append([
                key, str(v["n"]),
                f"{v['cov']/v['n']:.1%}",
                f"{v['cor']/v['n']:.1%}",
            ])
        _tbl(headers2, rows2, [14, 4, 8, 8])
        print()

    # Totals
    n_cov = sum(1 for p in evaluated if p["covered"])
    n_cor = sum(1 for p in evaluated if p["pick_correct"])
    print(f"  Totalt evaluert: {len(evaluated)}  |  Dekket: {n_cov}/{len(evaluated)} = {n_cov/len(evaluated):.1%}  |  Eksakt: {n_cor}/{len(evaluated)} = {n_cor/len(evaluated):.1%}")

    # Pick distribution (are we picking enough U and B?)
    print()
    print("  -- Pick-fordeling ---------------------------------------------")
    for sign in ["H", "U", "B"]:
        sub = [p for p in evaluated if p["pick"] == sign]
        if not sub:
            continue
        n_cov = sum(1 for p in sub if p["covered"])
        n_cor = sum(1 for p in sub if p["pick_correct"])
        bar   = _bar(n_cor / len(sub), 16)
        print(f"  {sign}: {len(sub):>3} picks  eksakt={n_cor/len(sub):.1%}  {bar}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Strategy Performance
# ══════════════════════════════════════════════════════════════════════════════

def report_strategy_performance(picks: list[dict], snapshots: list[dict]) -> None:
    _section("4. STRATEGY PERFORMANCE")
    print("  Sammenligner balanced / jackpot / safe over alle lagrede uker.")
    print()

    if not snapshots:
        _no_data("Ingen snapshots funnet."); return

    by_strat: dict[str, list] = defaultdict(list)
    for s in snapshots:
        by_strat[s["strategy"]].append(s)

    headers = ["Strategi  ", "Snaps", "Eval", "Dekket%", "Eksakt%", "Snitt-PVR", "Snitt-P(12)"]
    rows = []
    for strat in sorted(by_strat):
        slist = by_strat[strat]
        ev_snaps = [s for s in slist if s["n_evaluated"] > 0]
        tot_ev   = sum(s["n_evaluated"] for s in ev_snaps)
        tot_cov  = sum(s["n_covered"]   for s in ev_snaps)
        tot_cor  = sum(s["n_correct"]   for s in ev_snaps)
        avg_pvr  = sum((s["pvr"]  or 0) for s in slist) / len(slist)
        avg_pwin = sum((s["p_win"] or 0) for s in slist) / len(slist)
        rows.append([
            strat,
            str(len(slist)),
            str(tot_ev) if tot_ev else "-",
            f"{tot_cov/tot_ev:.1%}" if tot_ev else "-",
            f"{tot_cor/tot_ev:.1%}" if tot_ev else "-",
            f"{avg_pvr:.3f}",
            f"{avg_pwin:.3%}",
        ])
    _tbl(headers, rows, [11, 6, 5, 8, 8, 10, 12])

    # Per-week breakdown (only if multiple weeks)
    weeks = sorted(set((s["week"], s["year"]) for s in snapshots if s["week"]))
    if len(weeks) > 1:
        print()
        print("  -- Per uke -------------------------------------------------")
        headers2 = ["Uke/Ar", "Strategi  ", "Dekket%", "Eksakt%", "PVR  "]
        rows2 = []
        for wk, yr in weeks:
            for strat in sorted(by_strat):
                sub = [s for s in by_strat[strat] if s["week"] == wk and s["year"] == yr]
                if not sub:
                    continue
                tot_ev  = sum(s["n_evaluated"] for s in sub)
                tot_cov = sum(s["n_covered"]   for s in sub)
                tot_cor = sum(s["n_correct"]   for s in sub)
                avg_pvr = sum(s["pvr"] or 0 for s in sub) / len(sub)
                rows2.append([
                    f"{wk}/{yr}", strat,
                    f"{tot_cov/tot_ev:.1%}" if tot_ev else "-",
                    f"{tot_cor/tot_ev:.1%}" if tot_ev else "-",
                    f"{avg_pvr:.3f}",
                ])
        _tbl(headers2, rows2, [7, 11, 8, 8, 6])

    # Shape breakdown: does shape predict coverage?
    print()
    print("  -- Shape: treff per dekningsform per strategi ------------------")
    shape_stats: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "cov": 0, "cor": 0})
    for p in picks:
        if not p["has_result"]:
            continue
        key = (p["strategy"], p["coverage_type"])
        shape_stats[key]["n"]   += 1
        shape_stats[key]["cov"] += int(bool(p["covered"]))
        shape_stats[key]["cor"] += int(bool(p["pick_correct"]))

    headers3 = ["Strategi  ", "Dekningstype", "  N", "Dekket%", "Eksakt%"]
    rows3 = []
    for (strat, ct), v in sorted(shape_stats.items()):
        if not v["n"]:
            continue
        rows3.append([
            strat, ct, str(v["n"]),
            f"{v['cov']/v['n']:.1%}",
            f"{v['cor']/v['n']:.1%}",
        ])
    if rows3:
        _tbl(headers3, rows3, [11, 13, 4, 8, 8])
    else:
        print("  (Ingen evaluerte picks enda)")


# ══════════════════════════════════════════════════════════════════════════════
# 5. PVR Audit
# ══════════════════════════════════════════════════════════════════════════════

def report_pvr_audit(picks: list[dict], snapshots: list[dict]) -> None:
    _section("5. PVR AUDIT")
    print("  Korrelerer PVR (Pool Value Ratio) med faktisk dekning over tid?")
    print("  Hoy PVR = simulatoren tror omsetningen gir god verdi.")
    print()

    evaluated_snaps = [s for s in snapshots if s["n_evaluated"] > 0]
    if not evaluated_snaps:
        print("  -- Alle lagrede snapshots (ikke evaluert enda) ----------------")
        headers = ["Kupong              ", "Strategi  ", "PVR  ", "P(12)  ", "Dekning"]
        rows = []
        for s in sorted(snapshots, key=lambda x: x.get("pvr") or 0, reverse=True):
            rows.append([
                (s["coupon_id"] or "")[:20],
                s["strategy"],
                f"{s['pvr']:.3f}" if s["pvr"] else "-",
                f"{s['p_win']:.3%}" if s["p_win"] else "-",
                "ikke spilt enda",
            ])
        _tbl(headers, rows, [22, 11, 6, 8, 16])
        print()
        _no_data("Ingen evaluerte snapshots enda -- venter paa resultater.")
        return

    # All evaluated snapshots sorted by PVR
    print("  -- Evaluerte snapshots (sortert etter PVR) --------------------")
    headers = ["Kupong              ", "Strategi  ", "PVR  ", "P(12)  ", "Dekket ", "Dekn%"]
    rows = []
    for s in sorted(evaluated_snaps, key=lambda x: x.get("pvr") or 0, reverse=True):
        ev  = s["n_evaluated"]
        cov = s["n_covered"]
        rows.append([
            (s["coupon_id"] or "")[:20],
            s["strategy"],
            f"{s['pvr']:.3f}" if s["pvr"] else "-",
            f"{s['p_win']:.3%}" if s["p_win"] else "-",
            f"{cov}/{ev}",
            f"{cov/ev:.1%}" if ev else "-",
        ])
    _tbl(headers, rows, [22, 11, 6, 8, 8, 6])

    # Pearson correlation PVR <-> coverage_rate
    valid = [
        (s["pvr"], s["n_covered"] / s["n_evaluated"])
        for s in evaluated_snaps
        if s["pvr"] is not None and s["n_evaluated"] > 0
    ]
    if len(valid) >= 4:
        pvrs  = [v[0] for v in valid]
        covs  = [v[1] for v in valid]
        mp, mc = sum(pvrs) / len(pvrs), sum(covs) / len(covs)
        num   = sum((p - mp) * (c - mc) for p, c in zip(pvrs, covs))
        den   = (sum((p - mp)**2 for p in pvrs) * sum((c - mc)**2 for c in covs)) ** 0.5
        corr  = num / den if den else 0.0
        print()
        print(f"  Pearson-korrelasjon PVR <-> dekning: {corr:+.3f}")
        if   corr >  0.4: interp = "Positiv -- hoy PVR predikerer hoy dekning (hypotese holder)"
        elif corr < -0.4: interp = "Negativ -- hoy PVR predikerer LAVERE dekning (hypotese feil)"
        else:             interp = "Svak (<0.4) -- PVR korrelerer ikke med faktisk dekning enda"
        print(f"  Tolkning: {interp}")
        print(f"  (N={len(valid)} snapshots -- trenger ~10+ for robust konklusjon)")
    else:
        print()
        print(f"  (Trenger minst 4 evaluerte snapshots for korrelasjonsanalyse -- har {len(valid)})")

    # Calibration of p_win: was P(12) realistic?
    correct_snaps = [s for s in evaluated_snaps if s["n_evaluated"] == 12]
    if correct_snaps:
        print()
        print("  -- P(12)-kalibrering: var sannsynlighetene realistiske? -------")
        fully_covered = [s for s in correct_snaps if s["n_covered"] == 12]
        avg_pwin = sum(s["p_win"] for s in correct_snaps if s["p_win"]) / len(correct_snaps)
        actual_rate = len(fully_covered) / len(correct_snaps)
        print(f"  Fullt evaluerte snapshots: {len(correct_snaps)}")
        print(f"  Snitt P(12) fra simulator:  {avg_pwin:.3%}")
        print(f"  Faktisk 12/12-rate:         {actual_rate:.3%}  ({len(fully_covered)}/{len(correct_snaps)})")
        if len(correct_snaps) >= 10:
            ratio = actual_rate / avg_pwin if avg_pwin else None
            if ratio:
                print(f"  Ratio faktisk/simulert:     {ratio:.2f}x  {'(overvurderer)' if ratio < 0.8 else '(undervurderer)' if ratio > 1.2 else '(god kalibrering)'}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

REPORTS = {
    "calibration":    (report_calibration,       "picks"),
    "model_vs_public":(report_model_vs_public,    "picks"),
    "coverage":       (report_coverage_audit,     "picks"),
    "strategy":       (report_strategy_performance,"both"),
    "pvr":            (report_pvr_audit,           "both"),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="TippeIQ evidensbasert analysepipeline")
    parser.add_argument("--report",   choices=list(REPORTS), default=None,
                        help="Kjor kun en rapport (default: alle fem)")
    parser.add_argument("--week",     type=int,  default=None)
    parser.add_argument("--year",     type=int,  default=None)
    parser.add_argument("--strategy", type=str,  default=None, choices=["balanced","jackpot","safe"])
    parser.add_argument("--min-n",    type=int,  default=3,
                        help="Min picks per botte for aa vises (default: 3)")
    args = parser.parse_args()

    print()
    print("+" + "=" * (_W - 2) + "+")
    print("|" + "  TippeIQ -- Evidensbasert analysepipeline".center(_W - 2) + "|")
    print("+" + "=" * (_W - 2) + "+")

    filters = []
    if args.week:     filters.append(f"uke {args.week}")
    if args.year:     filters.append(f"ar {args.year}")
    if args.strategy: filters.append(f"strategi={args.strategy}")
    if filters:
        print(f"  Filter: {', '.join(filters)}")

    picks     = load_picks(week=args.week, year=args.year, strategy=args.strategy)
    snapshots = _build_snapshots(picks)

    n_eval  = sum(1 for p in picks if p["has_result"])
    n_snaps = len(snapshots)
    weeks   = sorted(set((p["week"], p["year"]) for p in picks if p["week"]))

    print(f"  Snapshots: {n_snaps}  |  Picks: {len(picks)}  |  Evaluert: {n_eval}")
    if weeks:
        lo, hi = weeks[0], weeks[-1]
        wk_str = f"uke {lo[0]}/{lo[1]}" if lo == hi else f"uke {lo[0]}/{lo[1]} --> {hi[0]}/{hi[1]}"
        print(f"  Data: {wk_str}")

    if not picks:
        print()
        print("  Ingen lagrede kupongsnapshots funnet.")
        print("  Lagre en kupong fra frontend, kjor evaluate.py --fetch, og provv igjen.")
        return

    run_all = args.report is None
    min_n   = args.min_n

    def run(name: str) -> None:
        fn, sig = REPORTS[name]
        if sig == "picks":
            fn(picks, min_n=min_n) if "min_n" in fn.__code__.co_varnames else fn(picks)
        else:
            fn(picks, snapshots)

    if run_all:
        for name in REPORTS:
            run(name)
    else:
        run(args.report)

    print()
    _hr()
    print("  Ferdig. Kjor 'evaluate.py --fetch' etter kampene er spilt for aa oppdatere.")
    print()


if __name__ == "__main__":
    main()
