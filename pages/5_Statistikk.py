"""
Statistikk — fixture analysis cards (redesigned Phase 8 UI).

Keeps all existing data loading and computation logic unchanged.
Only presentation is redesigned.
"""
from datetime import datetime as _dt
import json as _json
import streamlit as st
from db.schema import init_db
from db.coupon import list_coupons
from db.enrichment import get_coupon_enrichment
from models.match import Match as _MatchModel
from analysis.probability import process_match as _bm_prior
from analysis.model import run_model as _run_model
from analysis.estimated_prior import compute_estimated_prior as _est_prior
from analysis.pool_value import compute_value_index as _compute_vi

st.set_page_config(
    page_title="Statistikk — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] {
    background-color: #0b1623 !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
.block-container {
    max-width: 1320px !important;
    padding-top: 2.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
}

/* ── Page header ─────────────────────────────────────────── */
.stat-page-title { font-size:1.4rem; font-weight:900; color:#fff; margin-bottom:0.15rem; }
.stat-page-title .q { color:#f5c518; }
.stat-page-sub { font-size:0.72rem; color:#3a5a78; margin-bottom:1.5rem; }

/* ── Fixture card ────────────────────────────────────────── */
.fx-card {
    border:1px solid rgba(255,255,255,0.06);
    border-radius:12px;
    padding:18px 20px 16px;
    background:rgba(255,255,255,0.02);
    margin-bottom:16px;
}
.fx-card:hover { border-color:rgba(255,255,255,0.10); }

/* ── Match header ────────────────────────────────────────── */
.fx-match-header {
    display:flex; justify-content:space-between; align-items:flex-start;
    margin-bottom:14px; padding-bottom:12px;
    border-bottom:1px solid rgba(255,255,255,0.05);
}
.fx-match-num {
    font-size:10px; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1px;
    min-width:24px;
}
.fx-match-teams {
    font-size:1rem; font-weight:800; color:#e0eaf4;
    letter-spacing:-0.2px; flex:1; margin:0 12px;
}
.fx-match-meta {
    font-size:9px; color:#3a5a78; text-align:right; line-height:1.6;
}
.fx-match-comp {
    display:inline-block; font-size:8px; color:#3a5a78;
    padding:2px 7px; border:1px solid rgba(255,255,255,0.06);
    border-radius:10px; margin-top:3px;
}

/* ── Recommendation badge ────────────────────────────────── */
.fx-rec-block {
    display:flex; align-items:center; gap:10px; margin-bottom:14px;
}
.fx-rec-pick {
    font-size:1.6rem; font-weight:900; color:#f5c518;
    min-width:40px; text-align:center;
    line-height:1;
}
.fx-rec-meta { font-size:10px; color:#6a90b0; }
.fx-rec-meta strong { color:#c8ddf0; }
.conf-badge {
    font-size:10px; font-weight:700; padding:3px 10px;
    border-radius:6px; white-space:nowrap;
}

/* ── Probability bars ────────────────────────────────────── */
.prob-section { margin-bottom:14px; }
.prob-row {
    display:flex; align-items:center; gap:8px; margin-bottom:5px;
}
.prob-label {
    width:14px; font-size:10px; font-weight:700; color:#3a5a78;
    text-align:right; flex-shrink:0;
}
.prob-track {
    flex:1; height:8px; background:rgba(255,255,255,0.05);
    border-radius:4px; overflow:hidden;
}
.prob-fill-h { height:8px; background:#5096cc; border-radius:4px; }
.prob-fill-u { height:8px; background:#6a7a88; border-radius:4px; }
.prob-fill-b { height:8px; background:#c8960e; border-radius:4px; }
.prob-pct { width:36px; font-size:10px; color:#6a90b0; text-align:right; flex-shrink:0; }
.prob-rec-marker {
    width:14px; font-size:9px; color:#f5c518; text-align:center; flex-shrink:0;
}

/* ── Model vs Public ─────────────────────────────────────── */
.mvp-section { margin-bottom:14px; }
.mvp-title {
    font-size:9px; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1px;
    margin-bottom:8px;
}
.mvp-row {
    display:grid; grid-template-columns:60px 1fr 40px 50px;
    gap:6px; align-items:center; margin-bottom:6px;
}
.mvp-lbl { font-size:9px; color:#3a5a78; white-space:nowrap; }
.mvp-bar-wrap { height:6px; background:rgba(255,255,255,0.05); border-radius:3px; overflow:hidden; }
.mvp-bar-model { height:6px; background:#5096cc; border-radius:3px; }
.mvp-bar-public { height:6px; background:rgba(80,150,204,0.35); border-radius:3px; }
.mvp-pct { font-size:9px; color:#6a90b0; text-align:right; }
.mvp-diff {
    font-size:9px; font-weight:700; text-align:right;
}
.mvp-diff.pos { color:#3aaa78; }
.mvp-diff.neg { color:#e07a5f; }
.mvp-diff.neu { color:#3a5a78; }

/* ── Value/CDS block ─────────────────────────────────────── */
.value-block {
    display:grid; grid-template-columns:1fr 1fr 1fr;
    gap:10px; margin-bottom:14px;
}
.val-card {
    padding:10px 12px;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.05);
    border-radius:8px;
    text-align:center;
}
.val-card-num {
    font-size:1.1rem; font-weight:800;
    line-height:1.1; margin-bottom:3px;
}
.val-card-lbl { font-size:8px; color:#3a5a78; text-transform:uppercase; letter-spacing:0.8px; }

/* ── Signal badges ───────────────────────────────────────── */
.signal-row { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }
.sig-badge {
    display:flex; align-items:center; gap:4px;
    padding:4px 9px; border-radius:16px;
    font-size:9px; font-weight:700;
    border:1px solid;
}
.sig-ok   { background:rgba(58,170,120,0.12); color:#3aaa78; border-color:rgba(58,170,120,0.25); }
.sig-miss { background:rgba(46,74,100,0.15);  color:#2e4a64; border-color:rgba(46,74,100,0.25); }

/* ── Form badges ─────────────────────────────────────────── */
.form-row { display:flex; gap:4px; margin-top:3px; }
.fb { width:20px; height:20px; border-radius:4px; display:flex; align-items:center; justify-content:center; font-size:9px; font-weight:700; }
.fb-w { background:#0c2a14; color:#3aaa78; }
.fb-d { background:rgba(255,255,255,0.06); color:#6a90b0; }
.fb-l { background:#260c0c; color:#e07a5f; }

/* ── Expander ────────────────────────────────────────────── */
[data-testid="stExpander"] {
    border:1px solid rgba(255,255,255,0.05) !important;
    border-radius:8px !important;
    background:rgba(255,255,255,0.01) !important;
    margin-bottom:8px !important;
}
[data-testid="stExpander"] summary {
    font-size:9px !important; font-weight:700 !important;
    color:#3a5a78 !important; text-transform:uppercase !important;
    letter-spacing:1px !important;
}

/* ── Section label ───────────────────────────────────────── */
.stat-section-lbl {
    font-size:9px; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    padding:5px 0 10px; border-bottom:1px solid rgba(255,255,255,0.05);
    margin-bottom:14px;
}
.no-data-note {
    font-size:10px; color:#2e4a64;
    padding:10px 14px;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.04);
    border-radius:6px;
    margin-bottom:8px;
}
</style>
""", unsafe_allow_html=True)

# ── Page title ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="stat-page-title">Tippe<span class="q">Q</span>pongen — Statistikk</div>
<div class="stat-page-sub">Detaljert modellanalyse per kamp &middot; API-Football enrichment</div>
""", unsafe_allow_html=True)

# ── Data loading ──────────────────────────────────────────────────────────────
init_db()

_iso_now = _dt.now().isocalendar()
_all_coupons = list_coupons(week=_iso_now.week, year=_iso_now.year)
if not _all_coupons:
    st.info("Ingen kuponger i databasen for denne uken. Kjør sync.py --refresh-coupons.")
    st.stop()

_COUPON_DAY_LABELS = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
_tabs_labels = [
    _COUPON_DAY_LABELS.get(c.get("day_type", ""), c.get("coupon_id", "?").split("-")[0].capitalize())
    for c in _all_coupons
]
_tabs = st.tabs(_tabs_labels)

for _tab, _coupon in zip(_tabs, _all_coupons):
    with _tab:
        _coupon_id = _coupon["coupon_id"]
        _rows      = get_coupon_enrichment(_coupon_id)

        if not _rows:
            st.markdown(
                '<div class="no-data-note">Ingen enrichment-data for denne kupongen. Kjør: <code>python sync.py --daily</code></div>',
                unsafe_allow_html=True,
            )
            continue

        _n_with_af = sum(1 for r in _rows if r.get("has_api_football_data"))
        st.markdown(
            f'<div class="stat-section-lbl">{len(_rows)} kamper &middot; {_n_with_af} med API-Football data</div>',
            unsafe_allow_html=True,
        )

        for _row in _rows:
            _fix_num = _row.get("match_number", "?")
            _home    = _row.get("home_name", "?")
            _away    = _row.get("away_name", "?")
            _comp    = _row.get("arrangement_name") or _row.get("competition_id", "")
            _ko      = _row.get("kickoff_utc", "")
            _fix_id  = _row.get("api_football_fixture_id")

            # ── Build Match and run model (same logic as original Statistikk) ─
            _oh = _row.get("odds_h"); _ou = _row.get("odds_u"); _ob = _row.get("odds_b")
            _odds_src = _row.get("odds_source", "")

            # NT expert tips fallback (mirrors data/loader.py)
            if not (_oh and _ou and _ob):
                _ex_h = _row.get("expert_h"); _ex_u = _row.get("expert_u"); _ex_b = _row.get("expert_b")
                if (_ex_h and _ex_u and _ex_b
                        and float(_ex_h) > 0 and float(_ex_u) > 0 and float(_ex_b) > 0):
                    _oh = round(100.0 / float(_ex_h), 4)
                    _ou = round(100.0 / float(_ex_u), 4)
                    _ob = round(100.0 / float(_ex_b), 4)
                    _odds_src = "nt_expert"

            _odds_h = float(_oh or 3.0)
            _odds_u = float(_ou or 3.5)
            _odds_b = float(_ob or 3.0)

            # Public tips as probabilities
            _pb_h = _row.get("public_h"); _pb_u = _row.get("public_u"); _pb_b = _row.get("public_b")
            _has_pub = _pb_h is not None and _pb_u is not None and _pb_b is not None
            _has_exp = bool(_row.get("expert_h"))

            # Normalise public tips to probs
            _pub_h = _pub_u = _pub_b = None
            if _has_pub:
                _pb_sum = float(_pb_h) + float(_pb_u) + float(_pb_b)
                if _pb_sum > 0:
                    _pub_h = float(_pb_h) / _pb_sum
                    _pub_u = float(_pb_u) / _pb_sum
                    _pub_b = float(_pb_b) / _pb_sum

            _m = _MatchModel(
                number=_fix_num,
                home_team=_home,
                away_team=_away,
                odds_h=_odds_h,
                odds_u=_odds_u,
                odds_b=_odds_b,
                odds_source=_odds_src,
                pub_prob_h=_pub_h,
                pub_prob_u=_pub_u,
                pub_prob_b=_pub_b,
                has_public_tips=bool(_has_pub and _pub_h is not None),
                has_expert_tips=bool(_has_exp),
            )
            _bm_prior(_m)
            _m.bm_prob_h = _m.prob_h
            _m.bm_prob_u = _m.prob_u
            _m.bm_prob_b = _m.prob_b

            # Estimated prior fallback
            if not (_row.get("odds_h") or _row.get("expert_h")):
                _est_vals = _est_prior(_row)
                if _est_vals:
                    _m.prob_h = _est_vals.get("estimated_h", _m.prob_h)
                    _m.prob_u = _est_vals.get("estimated_u", _m.prob_u)
                    _m.prob_b = _est_vals.get("estimated_b", _m.prob_b)
                elif _row.get("estimated_h"):
                    _m.prob_h = float(_row["estimated_h"])
                    _m.prob_u = float(_row["estimated_u"])
                    _m.prob_b = float(_row["estimated_b"])

            _run_model(_m, _row)

            # Recommendation & confidence
            _rec  = _m.recommendation or "?"
            _conf = round(_m.confidence * 100, 1)

            # Confidence badge styling
            if _conf >= 60:   _cbg, _cfg = "#0c2a14", "#3ecf7a"
            elif _conf >= 52: _cbg, _cfg = "#122212", "#74c472"
            elif _conf >= 45: _cbg, _cfg = "#261c04", "#c8960e"
            else:             _cbg, _cfg = "#260c0c", "#be5050"

            # VI for recommended pick
            _rec_prob = {"H": _m.prob_h, "U": _m.prob_u, "B": _m.prob_b}.get(_rec)
            _rec_pub  = {"H": _m.pub_prob_h, "U": _m.pub_prob_u, "B": _m.pub_prob_b}.get(_rec)
            _vi = _compute_vi(_rec_prob or 0, _rec_pub)
            _vi_str = f"{_vi:.2f}&times;" if _vi else "&#8212;"
            _vi_col = "#3aaa78" if (_vi or 0) >= 1.25 else "#74cc9a" if (_vi or 0) >= 1.0 else "#e0956a" if (_vi or 0) >= 0.80 else "#e07a5f" if _vi else "#2e4a64"

            # CDS badge
            _cds_val = _m.crowd_disagreement_score
            if _cds_val is not None:
                if _cds_val >= 15:   _cds_lbl, _cds_col, _cds_bg = "Høy CDS", "#e07a5f", "#260c0c"
                elif _cds_val >= 7:  _cds_lbl, _cds_col, _cds_bg = "Middels CDS", "#c8960e", "#261c04"
                else:                _cds_lbl, _cds_col, _cds_bg = "Lav CDS", "#3aaa78", "#0c2a14"
            else:
                _cds_lbl, _cds_col, _cds_bg = "&#8212;", "#2e4a64", "transparent"

            # Value for recommended pick
            _rec_val = {"H": _m.value_h, "U": _m.value_u, "B": _m.value_b}.get(_rec)
            if _rec_val is not None and _has_pub:
                _vpp_str = f"{_rec_val:+.1f}pp"
                _vpp_col = "#3aaa78" if _rec_val > 0 else "#e07a5f"
                _vpp_bg  = "#0c2a14" if _rec_val > 0 else "#260c0c"
            else:
                _vpp_str, _vpp_col, _vpp_bg = "&#8212;", "#2e4a64", "transparent"

            # Format kickoff
            _ko_fmt = ""
            if _ko:
                try:
                    _ko_dt  = _dt.fromisoformat(_ko[:16])
                    _ko_fmt = _ko_dt.strftime("%d. %b %H:%M")
                except Exception:
                    _ko_fmt = _ko[:16]

            # ── Fixture card ──────────────────────────────────────────────────
            st.markdown(f"""
<div class="fx-card">
  <div class="fx-match-header">
    <div class="fx-match-num">#{_fix_num}</div>
    <div class="fx-match-teams">{_home} &ndash; {_away}</div>
    <div class="fx-match-meta">
      {_ko_fmt}
      {"<br><span class='fx-match-comp'>" + _comp + "</span>" if _comp else ""}
    </div>
  </div>

  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
    <div>
      <div class="fx-rec-block" style="margin-bottom:12px;">
        <div class="fx-rec-pick">{_rec}</div>
        <div class="fx-rec-meta">
          <span class="conf-badge" style="background:{_cbg};color:{_cfg};">{_conf:.0f}%</span>
          <div style="margin-top:4px;font-size:9px;color:#3a5a78;">Anbefalt utfall</div>
        </div>
      </div>

      <div class="prob-section">
        <div class="prob-row">
          <div class="prob-label">H</div>
          <div class="prob-track"><div class="prob-fill-h" style="width:{min(100,_m.prob_h*100):.0f}%;"></div></div>
          <div class="prob-pct">{_m.prob_h*100:.0f}%</div>
          <div class="prob-rec-marker">{"&#9733;" if _rec == "H" else ""}</div>
        </div>
        <div class="prob-row">
          <div class="prob-label">U</div>
          <div class="prob-track"><div class="prob-fill-u" style="width:{min(100,_m.prob_u*100):.0f}%;"></div></div>
          <div class="prob-pct">{_m.prob_u*100:.0f}%</div>
          <div class="prob-rec-marker">{"&#9733;" if _rec == "U" else ""}</div>
        </div>
        <div class="prob-row">
          <div class="prob-label">B</div>
          <div class="prob-track"><div class="prob-fill-b" style="width:{min(100,_m.prob_b*100):.0f}%;"></div></div>
          <div class="prob-pct">{_m.prob_b*100:.0f}%</div>
          <div class="prob-rec-marker">{"&#9733;" if _rec == "B" else ""}</div>
        </div>
      </div>
    </div>

    <div>
      <div class="value-block">
        <div class="val-card">
          <div class="val-card-num" style="color:{_vpp_col};">{_vpp_str}</div>
          <div class="val-card-lbl">Pool Value</div>
        </div>
        <div class="val-card">
          <div class="val-card-num" style="color:{_vi_col};">{_vi_str}</div>
          <div class="val-card-lbl">Verdiindeks</div>
        </div>
        <div class="val-card" style="background:{_cds_bg};border-color:{_cds_col}20;">
          <div class="val-card-num" style="color:{_cds_col};">{f"{_cds_val:.0f}" if _cds_val is not None else "&#8212;"}</div>
          <div class="val-card-lbl" style="color:{_cds_col};">{_cds_lbl}</div>
        </div>
      </div>
""", unsafe_allow_html=True)

            # Model vs Public comparison
            if _has_pub and _m.pub_prob_h is not None:
                _outcomes = [
                    ("H", _m.prob_h, _m.pub_prob_h or 0),
                    ("U", _m.prob_u, _m.pub_prob_u or 0),
                    ("B", _m.prob_b, _m.pub_prob_b or 0),
                ]
                mvp_rows = ""
                for _o, _mp, _pp in _outcomes:
                    _diff = (_mp - _pp) * 100
                    _diff_cls = "pos" if _diff > 1 else "neg" if _diff < -1 else "neu"
                    _diff_s = f"{_diff:+.0f}pp"
                    _w_model  = min(100, round(_mp * 100))
                    _w_public = min(100, round(_pp * 100))
                    mvp_rows += f"""
<div class="mvp-row">
  <div class="mvp-lbl">{_o} Mod/Folk</div>
  <div>
    <div class="mvp-bar-wrap" style="margin-bottom:2px;">
      <div class="mvp-bar-model" style="width:{_w_model}%;"></div>
    </div>
    <div class="mvp-bar-wrap">
      <div class="mvp-bar-public" style="width:{_w_public}%;"></div>
    </div>
  </div>
  <div class="mvp-pct">{_mp*100:.0f}%/{_pp*100:.0f}%</div>
  <div class="mvp-diff {_diff_cls}">{_diff_s}</div>
</div>"""
                st.markdown(
                    f'<div class="mvp-section"><div class="mvp-title">Modell vs Folket</div>{mvp_rows}</div>',
                    unsafe_allow_html=True,
                )

            # Signal badges — enrichment data comes as flat columns from get_coupon_enrichment
            _has_form  = bool(_row.get("home_form") or _row.get("away_form"))
            _has_ha    = bool(_row.get("home_home_record") or _row.get("away_away_record"))
            _has_goals = bool(_row.get("home_goals_for") or _row.get("away_goals_for"))
            _has_stand = bool(_row.get("home_position") or _row.get("away_position"))

            def _sig(label, ok):
                cls = "sig-ok" if ok else "sig-miss"
                icon = "&#10003;" if ok else "&#9675;"
                return f'<span class="sig-badge {cls}">{icon} {label}</span>'

            _sig_html = (
                _sig("Form", _has_form) +
                _sig("Hjemme/Borte", _has_ha) +
                _sig("Mål", _has_goals) +
                _sig("Tabell", _has_stand) +
                _sig("Ekspert", _has_exp) +
                _sig("Folket", _has_pub)
            )
            st.markdown(f'<div class="signal-row">{_sig_html}</div>', unsafe_allow_html=True)

            st.markdown('</div></div>', unsafe_allow_html=True)  # close grid + card

            # ── Advanced details expander (per fixture) ───────────────────────
            if _has_form or _has_exp or _has_goals or _has_stand:
                with st.expander(f"Detaljer — {_home} vs {_away}"):
                    # Form display
                    if _has_form:
                        st.markdown("**Form (siste 5)**", unsafe_allow_html=False)

                        def _form_badges(form_str: str) -> str:
                            html = '<div class="form-row">'
                            for ch in str(form_str)[:5]:
                                cls = "fb-w" if ch == "W" else "fb-l" if ch == "L" else "fb-d"
                                html += f'<div class="fb {cls}">{ch}</div>'
                            html += "</div>"
                            return html

                        _hf = _row.get("home_form", "")
                        _af = _row.get("away_form", "")
                        cols = st.columns(2)
                        if _hf:
                            cols[0].markdown(f"**{_home}**")
                            cols[0].markdown(_form_badges(_hf), unsafe_allow_html=True)
                        if _af:
                            cols[1].markdown(f"**{_away}**")
                            cols[1].markdown(_form_badges(_af), unsafe_allow_html=True)

                    # Raw probabilities
                    st.markdown("**Råsannsynligheter (modell)**")
                    st.markdown(
                        f"H: {_m.prob_h*100:.1f}%  ·  U: {_m.prob_u*100:.1f}%  ·  B: {_m.prob_b*100:.1f}%"
                    )
                    if getattr(_m, "bm_prob_h", None):
                        st.markdown(
                            f"BM prior — H: {_m.bm_prob_h*100:.1f}%  U: {_m.bm_prob_u*100:.1f}%  B: {_m.bm_prob_b*100:.1f}%"
                        )

                    # Standing data
                    if _has_stand:
                        st.markdown("**Tabellplassering**")
                        _hpos = _row.get("home_position", "?")
                        _apos = _row.get("away_position", "?")
                        st.markdown(f"{_home}: plass {_hpos}  ·  {_away}: plass {_apos}")

                    # Goals
                    if _has_goals:
                        st.markdown("**Mål**")
                        _hgs = _row.get("home_goals_for", "?")
                        _hgc = _row.get("home_goals_against", "?")
                        _ags = _row.get("away_goals_for", "?")
                        _agc = _row.get("away_goals_against", "?")
                        st.markdown(f"{_home}: {_hgs} scoret / {_hgc} sluppet inn  ·  {_away}: {_ags} scoret / {_agc} sluppet inn")

                    # Public tips detail
                    if _has_pub and _m.pub_prob_h is not None:
                        st.markdown("**Folkets tips**")
                        st.markdown(
                            f"H: {(_m.pub_prob_h or 0)*100:.0f}%  ·  U: {(_m.pub_prob_u or 0)*100:.0f}%  ·  B: {(_m.pub_prob_b or 0)*100:.0f}%"
                        )
                        if _m.crowd_pressure_pick:
                            st.markdown(f"Folkepresset på: **{_m.crowd_pressure_pick}**")

                    # API-Football ID
                    if _fix_id:
                        st.caption(f"API-Football fixture ID: {_fix_id}")
