"""
Odds Movement — time series of Pinnacle odds per fixture.

Shows for each fixture in a coupon:
  - Opening odds (first snapshot)
  - Saved coupon odds (from coupon_predictions)
  - Latest odds (most recent snapshot)
  - Closing odds (last snapshot before kickoff, if marked)
  - Movement direction and magnitude

Populate snapshots by running:
    python sync.py --odds-snapshot --week N --year YYYY

Mark closing odds after kickoff:
    python sync.py --mark-closing-odds
"""
import streamlit as st
from db.schema import init_db
from db.history import list_coupons_with_predictions
from db.odds_movement import (
    get_snapshot_summary_for_coupon,
    get_snapshots_for_fixture,
    get_clv_for_coupon,
)

st.set_page_config(
    page_title="Odds Movement — TippeQpongen",
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
.mov-table { width:100%; border-collapse:collapse; font-family:'Segoe UI',system-ui,Arial,sans-serif; font-size:11px; }
.mov-table th {
    font-size:9px; font-weight:700; color:#2e4a64; text-transform:uppercase; letter-spacing:1.1px;
    padding:6px 8px; background:rgba(255,255,255,0.04); border-bottom:1px solid rgba(255,255,255,0.07);
    text-align:left; white-space:nowrap;
}
.mov-table td { padding:5px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.025); vertical-align:middle; }
.mov-table tr:nth-child(even) td { background:rgba(255,255,255,0.015); }
.dim { color:#3a5a78; }
.up   { color:#3aaa78; font-weight:700; }
.down { color:#e74c3c; font-weight:700; }
.flat { color:#5a7a96; }
.clv-pos { color:#3aaa78; font-weight:700; }
.clv-neg { color:#e74c3c; font-weight:700; }
.snap-pill {
    display:inline-block; font-size:9px; padding:2px 6px; border-radius:3px;
    background:rgba(255,255,255,0.06); color:#5a7a96; margin-right:3px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Odds Movement</div>
<div class="page-subtitle">
Pinnacle odds over tid per kamp. Kj&#248;r <code>python sync.py --odds-snapshot</code>
daglig for a bygge opp historikk.
</div>
""", unsafe_allow_html=True)

init_db()

# ── Coupon selector ───────────────────────────────────────────────────────────────

all_coupons = list_coupons_with_predictions()
if not all_coupons:
    st.info(
        "Ingen kuponger med lagrede prediksjoner.\n\n"
        "Lagre en kupong pa hovedsiden (Lagre kupong) for a se odds-bevegelse."
    )
    st.stop()

_day_labels = {"MIDWEEK": "Midtuke", "SATURDAY": "Lordag", "SUNDAY": "Sondag"}

def _label(c: dict) -> str:
    dl = _day_labels.get(c.get("day_type", ""), c.get("day_type", "?"))
    return f"Uke {c['week']}/{c['year']} — {dl}  ({c['n_predictions']} tips)"

sel = st.selectbox(
    "Velg kupong",
    options=[c["coupon_id"] for c in all_coupons],
    format_func=lambda cid: _label(next(c for c in all_coupons if c["coupon_id"] == cid)),
)

# ── Summary table ─────────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Odds-bevegelse per kamp</div>', unsafe_allow_html=True)

summaries = get_snapshot_summary_for_coupon(sel)
clv_map   = {r["fixture_id"]: r for r in get_clv_for_coupon(sel)}

if not summaries or all(s["n_snapshots"] == 0 for s in summaries):
    st.info(
        "Ingen odds-snapshots funnet for denne kupongen.\n\n"
        f"Kj&#248;r: `python sync.py --odds-snapshot --week ... --year ...`"
    )
else:
    def _fmt(v, fallback="—"):
        return f"{v:.2f}" if v is not None else f'<span class="dim">{fallback}</span>'

    def _arrow(open_h, close_h, pick):
        """Show movement direction for the selected pick."""
        open_v  = open_h
        close_v = close_h
        if open_v is None or close_v is None:
            return '<span class="flat">—</span>'
        diff = close_v - open_v
        if abs(diff) < 0.01:
            return '<span class="flat">&#8596; flat</span>'
        if diff > 0:
            return f'<span class="up">&#8593; +{diff:.2f}</span>'
        return f'<span class="down">&#8595; {diff:.2f}</span>'

    rows_html = ""
    for s in summaries:
        fid     = s["fixture_id"]
        clv_d   = clv_map.get(fid, {})
        opening = s["opening"]
        latest  = s["latest"]
        closing = s["closing"]
        n_snaps = s["n_snapshots"]

        home_name = clv_d.get("home_name", "?")
        away_name = clv_d.get("away_name", "?")
        pick      = clv_d.get("recommended_pick", "?")

        # Odds for the selected pick column
        pick_idx = {"H": "h", "U": "u", "B": "b"}.get(pick, "h")
        open_pick   = opening[f"odds_{pick_idx}"]  if opening  else None
        latest_pick = latest[f"odds_{pick_idx}"]   if latest   else None
        close_pick  = closing[f"odds_{pick_idx}"]  if closing  else None
        saved_pick  = clv_d.get(f"pred_odds_{pick_idx}")

        arrow = _arrow(open_pick, close_pick or latest_pick, pick)

        clv_sel = clv_d.get("clv_selected")
        if clv_sel is not None:
            c_cls   = "clv-pos" if clv_sel >= 0 else "clv-neg"
            clv_str = f'<span class="{c_cls}">{clv_sel*100:+.1f}%</span>'
        else:
            clv_str = '<span class="dim">—</span>'

        snap_pill = f'<span class="snap-pill">{n_snaps} snap</span>'

        rows_html += (
            f"<tr>"
            f"<td style='white-space:nowrap'>{home_name} – {away_name}</td>"
            f"<td style='color:#f5c518;font-weight:700;text-align:center'>{pick}</td>"
            f"<td style='color:#5a7a96'>{_fmt(open_pick)}</td>"
            f"<td style='color:#c8ddf0'>{_fmt(saved_pick)}</td>"
            f"<td style='color:#c8ddf0'>{_fmt(latest_pick)}</td>"
            f"<td style='color:#8ab4d8'>{_fmt(close_pick)}</td>"
            f"<td>{arrow}</td>"
            f"<td style='text-align:center'>{clv_str}</td>"
            f"<td>{snap_pill}</td>"
            f"</tr>"
        )

    st.markdown(
        '<table class="mov-table"><thead><tr>'
        "<th>Kamp</th><th>Valg</th>"
        "<th>Apning</th><th>Lagret</th><th>Siste</th><th>Closing</th>"
        "<th>Bevegelse</th><th>CLV</th><th>Snapshots</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

# ── Full time series (expandable per fixture) ─────────────────────────────────────

st.markdown('<div class="section-head">Fullstendig tidsrekke per kamp</div>',
            unsafe_allow_html=True)

if not summaries:
    st.markdown('<p class="dim" style="font-size:12px">Ingen data.</p>', unsafe_allow_html=True)
else:
    for s in summaries:
        fid      = s["fixture_id"]
        clv_d    = clv_map.get(fid, {})
        home_nm  = clv_d.get("home_name", fid[:8])
        away_nm  = clv_d.get("away_name", "?")
        n_snaps  = s["n_snapshots"]

        if n_snaps == 0:
            continue

        with st.expander(f"{home_nm} – {away_nm}  ({n_snaps} snapshots)"):
            snaps = get_snapshots_for_fixture(fid)
            snap_rows = ""
            for sn in snaps:
                closing_lbl = " [closing]" if sn.get("is_closing_snapshot") else ""
                snap_rows += (
                    f"<tr>"
                    f"<td style='color:#3a5a78;font-size:10px'>{sn['fetched_at'][:16]}{closing_lbl}</td>"
                    f"<td>{sn['odds_h']:.2f}</td>"
                    f"<td>{sn['odds_u']:.2f}</td>"
                    f"<td>{sn['odds_b']:.2f}</td>"
                    f"<td style='color:#5a7a96;font-size:10px'>"
                    f"{sn['implied_prob_h']*100:.1f}% / "
                    f"{sn['implied_prob_u']*100:.1f}% / "
                    f"{sn['implied_prob_b']*100:.1f}%</td>"
                    f"<td style='color:#3a5a78;font-size:10px'>{sn['bookmaker']}</td>"
                    f"</tr>"
                )
            st.markdown(
                '<table class="mov-table"><thead><tr>'
                "<th>Tidspunkt</th><th>H</th><th>U</th><th>B</th>"
                "<th>Impl. sannsynlighet H/U/B</th><th>Bookmaker</th>"
                f"</tr></thead><tbody>{snap_rows}</tbody></table>",
                unsafe_allow_html=True,
            )
