"""
History — past coupon performance.

Shows evaluated coupons with hit rates, and a detail view per coupon.
"""
import json
import streamlit as st
from db.schema import init_db
from db.history import list_evaluated_coupons, list_coupons_with_predictions, get_results_for_coupon, get_evaluation
from db.odds_movement import get_clv_for_coupon

st.set_page_config(
    page_title="Historikk — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] { background-color: #0b1623 !important; border-bottom: 1px solid rgba(255,255,255,0.04) !important; }
.block-container { max-width: 1180px !important; padding-top: 2.5rem !important; }
.page-title { font-size: 1.4rem; font-weight: 900; color: #fff; margin-bottom: 0.2rem; }
.page-title .q { color: #f5c518; }
.page-subtitle { font-size: 0.75rem; color: #3a5a78; margin-bottom: 1.5rem; }
.section-head {
    font-size: 0.65rem; font-weight: 700; color: #2e4a64;
    text-transform: uppercase; letter-spacing: 1.8px;
    margin-bottom: 0.5rem; margin-top: 1.2rem;
    border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.3rem;
}
.hist-table { width:100%; border-collapse:collapse; font-family:'Segoe UI',system-ui,Arial,sans-serif; font-size:11.5px; }
.hist-table th {
    font-size:9px; font-weight:700; color:#2e4a64; text-transform:uppercase; letter-spacing:1.2px;
    padding:6px 8px; background:rgba(255,255,255,0.04); border-bottom:1px solid rgba(255,255,255,0.07);
    text-align:left; white-space:nowrap;
}
.hist-table td { padding:5px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.03); vertical-align:middle; }
.hist-table tr:nth-child(even) td { background:rgba(255,255,255,0.02); }
.hist-table .dim { color:#3a5a78; }
.badge { display:inline-block; font-size:9px; font-weight:700; padding:2px 7px; border-radius:4px; white-space:nowrap; }
.b-complete  { background:#0c2a14; color:#3aaa78; }
.b-partial   { background:#261c04; color:#c8960e; }
.b-pending   { background:#0c1e34; color:#5a7a96; }
.detail-table { width:100%; border-collapse:collapse; font-family:'Segoe UI',system-ui,Arial,sans-serif; font-size:11px; }
.detail-table th { font-size:9px; font-weight:700; color:#2e4a64; text-transform:uppercase; letter-spacing:1.1px; padding:6px 8px; background:rgba(255,255,255,0.04); border-bottom:1px solid rgba(255,255,255,0.07); white-space:nowrap; }
.detail-table td { padding:5px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.025); vertical-align:middle; }
.detail-table tr:nth-child(even) td { background:rgba(255,255,255,0.015); }
.tick  { color:#3aaa78; font-size:14px; }
.cross { color:#e74c3c; font-size:14px; }
.pick-covered { color:#3aaa78; font-weight:700; }
.pick-miss    { color:#e74c3c; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Historikk</div>
<div class="page-subtitle">Oversikt over tidligere kuponger og treffprosent.</div>
""", unsafe_allow_html=True)

init_db()

# ── Summary table: evaluated coupons ─────────────────────────────────────────────

_day_labels = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}
_status_badge = {
    "complete": '<span class="badge b-complete">Fullstendig</span>',
    "partial":  '<span class="badge b-partial">Delvis</span>',
    "pending":  '<span class="badge b-pending">Venter</span>',
}

st.markdown('<div class="section-head">Evaluerte kuponger</div>', unsafe_allow_html=True)

evaluated = list_evaluated_coupons()

if not evaluated:
    st.info(
        "Ingen evaluerte kuponger ennå.\n\n"
        "1. Lagre en kupong på hovedsiden (💾 Lagre kupong)\n"
        "2. Skriv inn resultater på **Resultater**-siden\n"
        "3. Kjør `python sync.py --evaluate`"
    )
else:
    rows_html = ""
    for e in evaluated:
        dl = _day_labels.get(e.get("day_type", ""), e.get("day_type", "—"))
        hit = f"{e['hit_rate']*100:.1f}%" if e.get("hit_rate") is not None else "—"
        cov = f"{e['cover_rate']*100:.1f}%" if e.get("cover_rate") is not None else "—"
        all12 = "✓" if e.get("all_12_correct") else ("✗" if e.get("evaluation_status") == "complete" else "—")
        correct = f"{e['correct_picks']}/{e['total_fixtures']}" if e.get("correct_picks") is not None else "—"
        badge = _status_badge.get(e.get("evaluation_status", ""), "")
        rows_html += (
            f"<tr>"
            f"<td>{e.get('week', '—')}</td>"
            f"<td>{e.get('year', '—')}</td>"
            f"<td>{dl}</td>"
            f"<td>{e.get('stake_nok', '—'):.0f} NOK</td>"
            f"<td>{e.get('total_rows', '—')}</td>"
            f"<td>{correct}</td>"
            f"<td>{hit}</td>"
            f"<td>{cov}</td>"
            f"<td style='text-align:center'>{all12}</td>"
            f"<td>{badge}</td>"
            f"</tr>"
        )
    st.markdown(
        '<table class="hist-table"><thead><tr>'
        "<th>Uke</th><th>År</th><th>Type</th><th>Innsats</th><th>Rekker</th>"
        "<th>Riktige tips</th><th>Treffprosent</th><th>Dekningsprosent</th>"
        "<th>12/12</th><th>Status</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

# ── Detail view ───────────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Kupongdetaljer</div>', unsafe_allow_html=True)

all_with_preds = list_coupons_with_predictions()

if not all_with_preds:
    st.markdown('<p style="color:#3a5a78;font-size:12px;">Ingen kuponger med lagrede prediksjoner.</p>',
                unsafe_allow_html=True)
else:
    def _coupon_label(c: dict) -> str:
        dl = _day_labels.get(c.get("day_type", ""), c.get("day_type", "?"))
        return f"Uke {c['week']}/{c['year']} — {dl}  ({c['n_predictions']} tips, {c['n_results']} resultater)"

    options = [c["coupon_id"] for c in all_with_preds]
    sel = st.selectbox(
        "Velg kupong",
        options=options,
        format_func=lambda cid: _coupon_label(next(c for c in all_with_preds if c["coupon_id"] == cid)),
    )

    rows    = get_results_for_coupon(sel)
    ev      = get_evaluation(sel)
    clv_map = {r["fixture_id"]: r for r in get_clv_for_coupon(sel)}

    if ev:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Riktige tips", f"{ev.get('correct_picks', '—')}/{ev.get('total_fixtures', 12)}")
        m2.metric("Treffprosent", f"{ev['hit_rate']*100:.1f}%" if ev.get("hit_rate") is not None else "—")
        m3.metric("Dekning", f"{ev['cover_rate']*100:.1f}%" if ev.get("cover_rate") is not None else "—")
        m4.metric("12/12", "Ja ✓" if ev.get("all_12_correct") else "Nei")

    # Compute average CLV across coupon where available
    clv_vals = [r["clv_selected"] for r in clv_map.values() if r.get("clv_selected") is not None]
    if clv_vals:
        avg_clv = sum(clv_vals) / len(clv_vals)
        clv_color = "#3aaa78" if avg_clv >= 0 else "#e74c3c"
        st.markdown(
            f'<p style="font-size:11px;color:{clv_color};margin-top:0.5rem;">'
            f'Gjennomsnittlig CLV: <strong>{avg_clv*100:+.1f}%</strong> '
            f'({len(clv_vals)} kamper med avslutningsodds)</p>',
            unsafe_allow_html=True,
        )

    # Per-fixture detail table
    detail_rows = ""
    for r in rows:
        fid    = r.get("fixture_id", "")
        result = r.get("result_1x2")
        home_s = r.get("home_score")
        away_s = r.get("away_score")
        score_str = f"{home_s}–{away_s}" if home_s is not None else "—"

        sel_outcomes = r.get("selected_outcomes", [])
        if isinstance(sel_outcomes, str):
            try:
                sel_outcomes = json.loads(sel_outcomes)
            except Exception:
                sel_outcomes = []

        picks_str = " / ".join(sel_outcomes) if sel_outcomes else "—"
        conf_str  = f"{r['confidence']*100:.1f}%" if r.get("confidence") else "—"

        if result and sel_outcomes:
            if result in sel_outcomes:
                picks_cell = f'<span class="pick-covered">{picks_str}</span>'
                check_cell = '<span class="tick">&#10003;</span>'
            else:
                picks_cell = f'<span class="pick-miss">{picks_str}</span>'
                check_cell = '<span class="cross">&#10007;</span>'
        else:
            picks_cell = picks_str
            check_cell = "—"

        result_cell = result if result else '<span class="dim">—</span>'

        odds_h = r.get("odds_h")
        odds_u = r.get("odds_u")
        odds_b = r.get("odds_b")
        odds_str = (
            f"{odds_h:.2f} / {odds_u:.2f} / {odds_b:.2f}"
            if all(x is not None for x in [odds_h, odds_u, odds_b])
            else '<span class="dim">—</span>'
        )

        # CLV cell
        clv_data = clv_map.get(fid)
        if clv_data and clv_data.get("clv_selected") is not None:
            clv_val = clv_data["clv_selected"]
            co_h = clv_data.get("closing_odds_h")
            co_u = clv_data.get("closing_odds_u")
            co_b = clv_data.get("closing_odds_b")
            closing_str = (
                f"{co_h:.2f}/{co_u:.2f}/{co_b:.2f}"
                if all(x is not None for x in [co_h, co_u, co_b])
                else "—"
            )
            clv_color = "#3aaa78" if clv_val >= 0 else "#e74c3c"
            clv_cell = (
                f'<span style="color:{clv_color};font-weight:700">{clv_val*100:+.1f}%</span>'
                f'<br><span style="font-size:9px;color:#3a5a78">{closing_str}</span>'
            )
        else:
            clv_cell = '<span class="dim">—</span>'

        detail_rows += (
            f"<tr>"
            f"<td style='color:#3a5a78'>{r['match_number']}</td>"
            f"<td style='white-space:nowrap'>{r.get('home_name','?')} – {r.get('away_name','?')}</td>"
            f"<td style='color:#5a7a96'>{odds_str}</td>"
            f"<td style='color:#f5c518;font-weight:700'>{r.get('recommended_pick','—')}</td>"
            f"<td style='color:#8ab4d8'>{conf_str}</td>"
            f"<td>{picks_cell}</td>"
            f"<td style='text-align:center;font-weight:700'>{result_cell}</td>"
            f"<td style='text-align:center'>{score_str}</td>"
            f"<td style='text-align:center'>{check_cell}</td>"
            f"<td style='text-align:center'>{clv_cell}</td>"
            f"</tr>"
        )

    st.markdown(
        '<table class="detail-table"><thead><tr>'
        "<th>#</th><th>Kamp</th><th>Lagrede odds H/U/B</th>"
        "<th>Tips</th><th>Konf.</th><th>Systemvalg</th>"
        "<th>Resultat</th><th>Score</th><th>Dekket</th>"
        "<th>CLV (avslutning)</th>"
        f"</tr></thead><tbody>{detail_rows}</tbody></table>",
        unsafe_allow_html=True,
    )

    if not rows:
        st.markdown('<p style="color:#3a5a78;font-size:12px">Ingen prediksjoner funnet.</p>',
                    unsafe_allow_html=True)
