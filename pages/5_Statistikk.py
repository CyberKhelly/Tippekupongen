"""
Statistikk — fixture analysis with optimizer decision.
Shows per-fixture model breakdown and closes the loop to the coupon recommendation.
"""
from datetime import datetime as _dt
import streamlit as st
from db.schema import init_db
from db.coupon import list_coupons
from db.enrichment import get_coupon_enrichment
from models.match import Match as _MatchModel
from analysis.probability import process_match as _bm_prior
from analysis.model import run_model as _run_model
from analysis.classifier import classify_match as _classify
from analysis.optimizer import optimize_coupon as _optimize
from analysis.estimated_prior import compute_estimated_prior as _est_prior
from analysis.pool_value import compute_value_index as _compute_vi

st.set_page_config(
    page_title="Statistikk — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background:#0b1623; }
[data-testid="stHeader"] {
    background:#0b1623 !important;
    border-bottom:1px solid rgba(255,255,255,0.04) !important;
}
.block-container {
    max-width:820px !important;
    padding-top:3rem !important;
    padding-left:2rem !important;
    padding-right:2rem !important;
}

/* ── Page header ─────────────────────────────────────────────── */
.stt-title {
    font-size:1rem; font-weight:900; color:#e8f2fc;
    letter-spacing:-.2px; margin-bottom:2px;
}
.stt-title .q { color:#f5c518; }
.stt-sub { font-size:.68rem; color:#2e4a64; margin-bottom:3rem; }

/* ── Tabs ────────────────────────────────────────────────────── */
[data-testid="stTabs"] button {
    font-size:.72rem !important; color:#3a5a78 !important;
    padding:6px 16px !important;
}
[data-testid="stTabs"] button[aria-selected="true"] {
    color:#e8f2fc !important;
}

/* ── Section label ───────────────────────────────────────────── */
.stt-sect {
    font-size:.62rem; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    margin-bottom:2.5rem;
}

/* ── Fixture wrapper — no box, only a thin top rule ─────────── */
.fx {
    padding:32px 0 8px;
    border-top:1px solid rgba(255,255,255,0.05);
    position:relative;
    padding-left:18px;
}
.fx:first-child { border-top:none; padding-top:8px; }

/* ── Left accent stripe ──────────────────────────────────────── */
.fx-accent {
    position:absolute; left:0; top:40px;
    width:2px; height:48px; border-radius:2px;
    opacity:.8;
}
.fx-a-h { background:linear-gradient(180deg,#5096cc 0%,transparent 100%); }
.fx-a-u { background:linear-gradient(180deg,#6a7a88 0%,transparent 100%); }
.fx-a-b { background:linear-gradient(180deg,#c8960e 0%,transparent 100%); }

/* ── Meta row ────────────────────────────────────────────────── */
.fx-meta {
    display:flex; align-items:center; gap:6px;
    margin-bottom:8px;
}
.fx-num  { font-size:.62rem; font-weight:700; color:#2e4a64; }
.fx-dot  { font-size:.55rem; color:#1a3040; }
.fx-comp { font-size:.62rem; color:#2e4a64; }
.fx-ko   { font-size:.62rem; color:#1e3448; margin-left:auto; }

/* ── Team names ──────────────────────────────────────────────── */
.fx-teams {
    font-size:1.55rem; font-weight:800; color:#e8f2fc;
    letter-spacing:-.5px; line-height:1.05;
    margin-bottom:28px;
}
.fx-vs { color:#1a2e40; font-weight:300; margin:0 10px; font-size:1.2rem; }

/* ── Hero block ──────────────────────────────────────────────── */
.fx-conf-num {
    font-size:4.2rem; font-weight:900;
    letter-spacing:-3px; line-height:1;
    margin-bottom:6px;
}
.fx-pick-lbl {
    font-size:.65rem; font-weight:700; color:#607888;
    text-transform:uppercase; letter-spacing:2px;
    margin-bottom:20px;
}

/* ── Pills ───────────────────────────────────────────────────── */
.fx-pills { display:flex; gap:7px; flex-wrap:wrap; margin-bottom:32px; }
.fx-pill {
    font-size:.7rem; font-weight:700;
    padding:4px 11px; border-radius:20px;
    border:1px solid; white-space:nowrap; line-height:1.4;
}
.pill-pos  { color:#3aaa78; border-color:rgba(58,170,120,.28); background:rgba(58,170,120,.06); }
.pill-neg  { color:#e07a5f; border-color:rgba(224,122,95,.28); background:rgba(224,122,95,.06); }
.pill-gold { color:#f5c518; border-color:rgba(245,197,24,.28); background:rgba(245,197,24,.06); }
.pill-neu  { color:#8aabb8; border-color:rgba(138,171,184,.15); background:rgba(138,171,184,.03); }
.pill-dim  { color:#3a5a78; border-color:rgba(58,90,120,.18); background:transparent; }

/* ── Model vs Public ─────────────────────────────────────────── */
.mvp-lbl {
    font-size:.6rem; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    margin-bottom:14px;
}
.mvp-row {
    display:grid;
    grid-template-columns:16px 80px 80px 1fr 48px;
    gap:10px; align-items:center; margin-bottom:10px;
}
.mvp-out { font-size:.72rem; font-weight:700; color:#3a5a78; }
.mvp-out-rec { color:#e8f2fc; }
.mvp-pct { font-size:.68rem; color:#607888; text-align:right; }
.mvp-pct-rec { color:#c8ddf0; font-weight:700; }
.mvp-bar { position:relative; height:2px; border-radius:2px; background:rgba(255,255,255,.05); }
.mvp-delta { font-size:.72rem; font-weight:800; text-align:right; }
.mvp-section { margin-bottom:30px; }

/* ── Evidence ────────────────────────────────────────────────── */
.ev-lbl {
    font-size:.6rem; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    margin-bottom:14px;
}
.ev-team-row {
    display:flex; align-items:center; gap:10px;
    margin-bottom:10px; flex-wrap:wrap;
}
.ev-name { font-size:.78rem; font-weight:700; color:#c8ddf0; min-width:110px; }
.ev-pos {
    font-size:.62rem; font-weight:700; color:#607888;
    background:rgba(255,255,255,.03);
    border:1px solid rgba(255,255,255,.06);
    padding:1px 6px; border-radius:8px;
}
.ev-badges { display:flex; gap:3px; }
.fb {
    display:inline-flex; align-items:center; justify-content:center;
    width:19px; height:19px; border-radius:3px;
    font-size:.6rem; font-weight:700;
}
.fb-w { background:#0c2a14; color:#3aaa78; }
.fb-d { background:rgba(255,255,255,.05); color:#5a7a90; }
.fb-l { background:#260c0c; color:#e07a5f; }
.ev-rec { font-size:.62rem; color:#2e4a64; }
.ev-goals { font-size:.62rem; color:#2e4a64; }
.ev-section { margin-bottom:20px; }

/* ── Expander — strip style, no box ─────────────────────────── */
[data-testid="stExpander"] {
    border:none !important;
    border-top:1px solid rgba(255,255,255,0.04) !important;
    border-radius:0 !important;
    background:transparent !important;
    margin-top:12px !important;
    margin-bottom:0 !important;
}
[data-testid="stExpander"] summary {
    font-size:.62rem !important; font-weight:600 !important;
    color:#1e3448 !important; letter-spacing:.5px !important;
    padding:10px 0 !important;
    text-transform:uppercase !important;
}
[data-testid="stExpander"] summary:hover { color:#3a5a78 !important; }
[data-testid="stExpander"] > div[data-testid="stExpanderDetails"] {
    padding:8px 0 16px !important;
}

/* ── Advanced table ──────────────────────────────────────────── */
.adv-head {
    display:grid; grid-template-columns:32px 1fr 1fr 1fr;
    gap:10px; padding:4px 0 8px;
    border-bottom:1px solid rgba(255,255,255,.04);
    font-size:.58rem; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1px;
}
.adv-row {
    display:grid; grid-template-columns:32px 1fr 1fr 1fr;
    gap:10px; align-items:center; padding:7px 0;
    border-bottom:1px solid rgba(255,255,255,.025);
    font-size:.7rem;
}
.adv-out { color:#3a5a78; font-weight:700; }
.adv-out-rec { color:#e8f2fc; font-weight:800; }
.adv-val { color:#607888; text-align:right; }
.adv-val-rec { color:#c8ddf0; font-weight:700; text-align:right; }
.adv-meta { font-size:.6rem; color:#1e3448; padding-top:10px; line-height:2; }
</style>
""", unsafe_allow_html=True)

# ── Page title ────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="stt-title">Tippe<span class="q">Q</span>pongen — Statistikk</div>'
    '<div class="stt-sub">Per-kamp modellanalyse &middot; optimizer-beslutning</div>',
    unsafe_allow_html=True,
)

# ── Data loading ──────────────────────────────────────────────────────────────
init_db()
_iso_now     = _dt.now().isocalendar()
_all_coupons = list_coupons(week=_iso_now.week, year=_iso_now.year)
if not _all_coupons:
    st.info("Ingen kuponger i databasen. Kjør sync.py --refresh-coupons.")
    st.stop()

# ── Strategy selector ─────────────────────────────────────────────────────────
_stt_strat_options = ["safe", "balanced", "jackpot"]
_stt_default = st.session_state.get("strategy", "balanced")
if _stt_default not in _stt_strat_options:
    _stt_default = "balanced"
_stt_strategy = st.radio(
    "Strategi",
    options=_stt_strat_options,
    index=_stt_strat_options.index(_stt_default),
    format_func=lambda s: {
        "safe": "Safe", "balanced": "Balansert", "jackpot": "Jackpot",
    }[s],
    horizontal=True,
    label_visibility="collapsed",
)

_DAY_LBL = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
_tabs = st.tabs([
    _DAY_LBL.get(c.get("day_type", ""), c.get("coupon_id", "?").split("-")[0].capitalize())
    for c in _all_coupons
])

for _tab, _coupon in zip(_tabs, _all_coupons):
    with _tab:
        _coupon_id = _coupon["coupon_id"]
        _rows      = get_coupon_enrichment(_coupon_id)

        if not _rows:
            st.markdown(
                '<div style="font-size:.72rem;color:#2e4a64;padding:20px 0;">'
                'Ingen enrichment-data. Kjør: <code>python sync.py --daily</code></div>',
                unsafe_allow_html=True,
            )
            continue

        _n_af = sum(1 for r in _rows if r.get("has_api_football_data"))
        st.markdown(
            f'<div class="stt-sect">{len(_rows)} kamper &middot; {_n_af} med API-Football</div>',
            unsafe_allow_html=True,
        )

        # ── Pass 1: build + classify all match objects ────────────────────────
        _match_triples = []   # (row, match, resolved_odds_src)
        for _row in _rows:
            _fix_num  = _row.get("match_number", "?")
            _home     = _row.get("home_name", "?")
            _away     = _row.get("away_name", "?")
            _odds_src = _row.get("odds_source", "")

            _oh = _row.get("odds_h"); _ou = _row.get("odds_u"); _ob = _row.get("odds_b")

            _odds_h = float(_oh or 3.0)
            _odds_u = float(_ou or 3.5)
            _odds_b = float(_ob or 3.0)

            _pb_h = _row.get("public_h"); _pb_u = _row.get("public_u"); _pb_b = _row.get("public_b")
            _has_pub = _pb_h is not None and _pb_u is not None and _pb_b is not None
            _has_exp = bool(_row.get("expert_h"))

            _pub_h = _pub_u = _pub_b = None
            if _has_pub:
                _pb_sum = float(_pb_h) + float(_pb_u) + float(_pb_b)
                if _pb_sum > 0:
                    _pub_h = float(_pb_h) / _pb_sum
                    _pub_u = float(_pb_u) / _pb_sum
                    _pub_b = float(_pb_b) / _pb_sum

            _m = _MatchModel(
                number=_fix_num, home_team=_home, away_team=_away,
                odds_h=_odds_h, odds_u=_odds_u, odds_b=_odds_b,
                odds_source=_odds_src,
                pub_prob_h=_pub_h, pub_prob_u=_pub_u, pub_prob_b=_pub_b,
                has_public_tips=bool(_has_pub and _pub_h is not None),
                has_expert_tips=bool(_has_exp),
            )
            _bm_prior(_m)
            _m.bm_prob_h = _m.prob_h
            _m.bm_prob_u = _m.prob_u
            _m.bm_prob_b = _m.prob_b

            if not _row.get("odds_h"):
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
            _classify(_m)
            _match_triples.append((_row, _m, _odds_src))

        # ── Run optimizer for selected strategy ───────────────────────────────
        _opt_picks, _ = _optimize(
            [_m for _, _m, _ in _match_triples],
            192.0,
            strategy=_stt_strategy,
        )

        # ── Pass 2: render ────────────────────────────────────────────────────
        for _row, _m, _odds_src in _match_triples:
            _fix_num  = _row.get("match_number", "?")
            _home     = _row.get("home_name", "?")
            _away     = _row.get("away_name", "?")
            _comp     = _row.get("arrangement_name") or _row.get("competition_id", "")
            _ko       = _row.get("kickoff_utc", "")
            _fix_id   = _row.get("api_football_fixture_id")
            _has_pub  = _m.has_public_tips
            _has_exp  = _m.has_expert_tips

            _rec  = _m.recommendation or "?"
            _conf = round(_m.confidence * 100, 1)

            # Derived values
            _rec_prob = {"H": _m.prob_h, "U": _m.prob_u, "B": _m.prob_b}.get(_rec)
            _rec_pub  = {"H": _m.pub_prob_h, "U": _m.pub_prob_u, "B": _m.pub_prob_b}.get(_rec)
            _vi       = _compute_vi(_rec_prob or 0, _rec_pub)
            _rec_val  = {"H": _m.value_h, "U": _m.value_u, "B": _m.value_b}.get(_rec)
            _cds_val  = _m.crowd_disagreement_score

            # Confidence colour
            _conf_col = "#3aaa78" if _conf >= 60 else "#c8960e" if _conf >= 45 else "#be5050"

            # Left accent class
            _acc_cls = {"H": "fx-a-h", "U": "fx-a-u", "B": "fx-a-b"}.get(_rec, "fx-a-u")

            # Pick label
            _pick_lbl = {"H": "HJEMMESEIER", "U": "UAVGJORT", "B": "BORTESEIER"}.get(_rec, _rec)

            # Kickoff format
            _ko_fmt = ""
            if _ko:
                try:
                    _ko_fmt = _dt.fromisoformat(_ko[:16]).strftime("%d. %b %H:%M")
                except Exception:
                    _ko_fmt = _ko[:16]

            # ── Pills ─────────────────────────────────────────────────────────
            _pills_html = ""
            if _rec_val is not None and _has_pub:
                _pc = "pill-pos" if _rec_val > 2 else "pill-neg" if _rec_val < -2 else "pill-neu"
                _pills_html += f'<span class="fx-pill {_pc}">{_rec_val:+.0f}pp Edge</span>'
            if _vi:
                _vc = "pill-gold" if _vi >= 1.25 else "pill-pos" if _vi >= 1.0 else "pill-neg"
                _pills_html += f'<span class="fx-pill {_vc}">{_vi:.2f}&times; VI</span>'
            if _cds_val is not None:
                _dc = "pill-neg" if _cds_val >= 15 else "pill-neu" if _cds_val >= 7 else "pill-dim"
                _pills_html += f'<span class="fx-pill {_dc}">CDS {_cds_val:.0f}</span>'
            if not _has_pub:
                _pills_html += f'<span class="fx-pill pill-dim">{_odds_src or "bookmaker"}</span>'

            # ── Meta row ─────────────────────────────────────────────────────
            _meta_parts = [f'<span class="fx-num">#{_fix_num}</span>']
            if _comp:
                _meta_parts += [
                    '<span class="fx-dot">·</span>',
                    f'<span class="fx-comp">{_comp}</span>',
                ]
            if _ko_fmt:
                _meta_parts.append(f'<span class="fx-ko">{_ko_fmt}</span>')

            # ── Model vs Public ───────────────────────────────────────────────
            _mvp_html = ""
            if _has_pub and _m.pub_prob_h is not None:
                _mvp_rows = ""
                for _o, _mp, _pp in [
                    ("H", _m.prob_h, _m.pub_prob_h or 0),
                    ("U", _m.prob_u, _m.pub_prob_u or 0),
                    ("B", _m.prob_b, _m.pub_prob_b or 0),
                ]:
                    _d   = (_mp - _pp) * 100
                    _dc  = "#3aaa78" if _d > 2 else "#e07a5f" if _d < -2 else "#2e4a64"
                    _oc  = "mvp-out-rec" if _o == _rec else "mvp-out"
                    _wm  = round(_mp * 100)
                    _wp  = round(_pp * 100)
                    _mvp_rows += (
                        f'<div class="mvp-row">'
                        f'<span class="{_oc}">{_o}</span>'
                        f'<div style="font-size:.68rem;color:#607888;text-align:right;">'
                        f'Modell <span style="color:#8aabb8;font-weight:700;">{_wm}%</span></div>'
                        f'<div style="font-size:.68rem;color:#607888;text-align:right;">'
                        f'Folket <span style="color:rgba(200,150,14,.7);font-weight:700;">{_wp}%</span></div>'
                        f'<div class="mvp-bar">'
                        f'<div style="position:absolute;left:0;top:0;height:2px;width:{_wm}%;'
                        f'background:#5096cc;border-radius:2px;"></div>'
                        f'<div style="position:absolute;left:0;top:0;height:2px;width:{_wp}%;'
                        f'background:rgba(200,150,14,.45);border-radius:2px;"></div>'
                        f'</div>'
                        f'<span class="mvp-delta" style="color:{_dc};">{_d:+.0f}pp</span>'
                        f'</div>'
                    )
                _mvp_html = (
                    f'<div class="mvp-section">'
                    f'<div class="mvp-lbl">Modell vs. Folket</div>'
                    f'{_mvp_rows}'
                    f'</div>'
                )

            # ── Team evidence ─────────────────────────────────────────────────
            _hf_str = str(_row.get("home_form", "") or "")
            _af_str = str(_row.get("away_form", "") or "")
            _hpos   = _row.get("home_position")
            _apos   = _row.get("away_position")
            _hgf    = _row.get("home_goals_for")
            _hgc    = _row.get("home_goals_against")
            _agf    = _row.get("away_goals_for")
            _agc    = _row.get("away_goals_against")
            _hhr    = str(_row.get("home_home_record", "") or "")
            _aar    = str(_row.get("away_away_record", "") or "")

            _has_form  = bool(_hf_str or _af_str)
            _has_goals = bool(_hgf or _agf)
            _has_stand = bool(_hpos or _apos)
            _has_ha    = bool(_hhr or _aar)

            def _fbadges(fs):
                if not fs: return ""
                out = '<span class="ev-badges">'
                for ch in str(fs)[:5]:
                    cls = "fb-w" if ch == "W" else "fb-l" if ch == "L" else "fb-d"
                    out += f'<span class="fb {cls}">{ch}</span>'
                return out + '</span>'

            def _ev_team(name, pos, form_s, record, gf, gc):
                h = '<div class="ev-team-row">'
                h += f'<span class="ev-name">{name}</span>'
                if pos:
                    h += f'<span class="ev-pos">#{pos}</span>'
                if form_s:
                    h += _fbadges(form_s)
                if record:
                    h += f'<span class="ev-rec">{record}</span>'
                try:
                    h += f'<span class="ev-goals">{int(float(gf))}&thinsp;/&thinsp;{int(float(gc))}</span>'
                except Exception:
                    pass
                h += '</div>'
                return h

            _ev_html = ""
            if _has_form or _has_stand or _has_goals or _has_ha:
                _ev_html = (
                    f'<div class="ev-section">'
                    f'<div class="ev-lbl">Lag</div>'
                    + _ev_team(_home, _hpos, _hf_str, _hhr, _hgf, _hgc)
                    + _ev_team(_away, _apos, _af_str, _aar, _agf, _agc)
                    + '</div>'
                )

            # ── Conviction vs. necessary ──────────────────────────────────────
            _is_conviction = (
                _has_pub and _rec_val is not None and abs(_rec_val) >= 10.0
            )

            # ── Claim sentence ────────────────────────────────────────────────
            if _has_pub and _rec_val is not None:
                if _is_conviction:
                    _subject = (
                        f"hjemmelaget ({_home})" if _rec == "H"
                        else f"bortelaget ({_away})" if _rec == "B"
                        else "uavgjort"
                    )
                    _direction = "undervurderer" if _rec_val > 0 else "overvurderer"
                    _claim = f"Folket {_direction} {_subject} med {abs(_rec_val):.0f}pp."
                else:
                    _claim = f"Modell og marked er i stor grad enige ({_rec_val:+.0f}pp). Anbefaling: {_rec} med {_conf:.0f}%."
            else:
                _claim = f"Ingen offentlig tipsprosent. Modellen anbefaler {_rec} med {_conf:.0f}% konfidens."

            # ── Optimizer decision block ──────────────────────────────────────
            _picks_this = _opt_picks.get(_m.number, [_rec])
            _n_p = len(_picks_this)
            _cov_lbl = {1: "Banker", 2: "Halvdekk", 3: "Heldekkende"}.get(_n_p, "?")
            _cov_col = {1: "#3a5a78", 2: "#c8960e", 3: "#be5050"}.get(_n_p, "#3a5a78")
            _picks_str = " + ".join(_picks_this)
            if _n_p == 1:
                _opt_reason = f"konfidens {_conf:.0f}% — uten ekstra dekning"
            elif _n_p == 2 and _cds_val is not None and _cds_val >= 10:
                _opt_reason = f"CDS {_cds_val:.0f} — folkeavvik utløste halvdekk"
            elif _n_p == 2:
                _opt_reason = "halvdekk innenfor budsjettramme"
            else:
                _opt_reason = f"full dekning — konfidens {_conf:.0f}%"
            _opt_html = (
                f'<div style="font-size:.68rem;margin-bottom:16px;'
                f'border-left:2px solid {_cov_col};padding-left:10px;">'
                f'<span style="font-size:.58rem;font-weight:700;color:{_cov_col};'
                f'text-transform:uppercase;letter-spacing:.5px;">Optimizer</span>'
                f'&nbsp;&nbsp;'
                f'<span style="color:#8aabb8;font-weight:600;">{_cov_lbl}</span>'
                f'&nbsp;·&nbsp;{_picks_str}'
                f'&nbsp;&nbsp;<span style="color:#2e4a64;">{_opt_reason}</span>'
                f'</div>'
            )

            # ── Focal block: edge (conviction) or confidence (necessary) ──────
            if _is_conviction:
                _edge_col2 = "#f5c518" if _rec_val > 0 else "#e07a5f"
                _pub_pct   = round((_rec_pub or 0) * 100)
                _mod_pct   = round((_rec_prob or 0) * 100)
                _focal_html = (
                    f'<div style="display:flex;align-items:flex-end;gap:32px;margin-bottom:20px;">'
                    f'<div>'
                    f'<div style="font-size:3.2rem;font-weight:900;letter-spacing:-2px;line-height:1;'
                    f'color:{_edge_col2};font-variant-numeric:tabular-nums;">{_rec_val:+.0f}pp</div>'
                    f'<div style="font-size:.6rem;font-weight:700;color:#2e4a64;text-transform:uppercase;'
                    f'letter-spacing:2px;margin-top:4px;">Markedsavvik</div>'
                    f'</div>'
                    f'<div style="display:flex;flex-direction:column;gap:8px;padding-bottom:4px;">'
                    f'<div style="display:flex;align-items:baseline;gap:6px;">'
                    f'<span style="font-size:1.4rem;font-weight:800;color:#e8f2fc;">{_mod_pct}%</span>'
                    f'<span style="font-size:.62rem;color:#3a5a78;text-transform:uppercase;letter-spacing:.8px;">Modell</span>'
                    f'</div>'
                    f'<div style="display:flex;align-items:baseline;gap:6px;">'
                    f'<span style="font-size:1.4rem;font-weight:800;color:rgba(200,150,14,0.7);">{_pub_pct}%</span>'
                    f'<span style="font-size:.62rem;color:#3a5a78;text-transform:uppercase;letter-spacing:.8px;">Marked</span>'
                    f'</div>'
                    f'</div>'
                    f'</div>'
                )
            else:
                _focal_html = (
                    f'<div style="display:flex;align-items:flex-end;gap:24px;margin-bottom:20px;">'
                    f'<div>'
                    f'<div style="font-size:2.4rem;font-weight:900;letter-spacing:-1px;line-height:1;'
                    f'color:{_conf_col};font-variant-numeric:tabular-nums;">{_conf:.0f}%</div>'
                    f'<div style="font-size:.6rem;font-weight:700;color:#2e4a64;text-transform:uppercase;'
                    f'letter-spacing:2px;margin-top:4px;">Konfidens</div>'
                    f'</div>'
                    f'<div style="padding-bottom:4px;">'
                    f'<div style="font-size:1.1rem;font-weight:800;color:#607888;">{_pick_lbl}</div>'
                    f'{"<div style=\"font-size:.62rem;color:#1e3448;margin-top:4px;\">Markedsavvik: " + f"{_rec_val:+.0f}pp</div>" if _rec_val is not None and _has_pub else ""}'
                    f'</div>'
                    f'</div>'
                )

            # ── Supporting pills (VI, CDS only) ──────────────────────────────
            _supp_pills = ""
            if _vi:
                _vc = "pill-gold" if _vi >= 1.25 else "pill-pos" if _vi >= 1.0 else "pill-neg"
                _supp_pills += f'<span class="fx-pill {_vc}">{_vi:.2f}&times; VI</span>'
            if _cds_val is not None:
                _dc = "pill-neg" if _cds_val >= 15 else "pill-neu" if _cds_val >= 7 else "pill-dim"
                _supp_pills += f'<span class="fx-pill {_dc}">CDS {_cds_val:.0f}</span>'
            if _supp_pills:
                _supp_pills = f'<div class="fx-pills" style="margin-bottom:24px;">{_supp_pills}</div>'

            # ── Render fixture ────────────────────────────────────────────────
            st.markdown(
                f'<div class="fx">'
                f'<div class="fx-accent {_acc_cls}"></div>'
                f'<div class="fx-meta">{"".join(_meta_parts)}</div>'
                f'<div class="fx-teams">{_home}<span class="fx-vs">—</span>{_away}</div>'
                f'<div style="font-size:.88rem;color:#8aabb8;line-height:1.6;margin-bottom:12px;'
                f'font-style:italic;">{_claim}</div>'
                f'{_opt_html}'
                f'{_focal_html}'
                f'{_supp_pills}'
                f'{_ev_html}'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Advanced expander ─────────────────────────────────────────────
            with st.expander("Detaljert analyse"):
                _exp_h = _row.get("expert_h")
                _exp_u = _row.get("expert_u")
                _exp_b = _row.get("expert_b")

                _adv_body = (
                    f'<div class="adv-head">'
                    f'<span></span><span style="text-align:right;">Modell</span>'
                    f'<span style="text-align:right;">Folket</span>'
                    f'<span style="text-align:right;">Ekspert</span>'
                    f'</div>'
                )
                for _o, _mp, _pp, _ep_raw in [
                    ("H", _m.prob_h, _m.pub_prob_h, _exp_h),
                    ("U", _m.prob_u, _m.pub_prob_u, _exp_u),
                    ("B", _m.prob_b, _m.pub_prob_b, _exp_b),
                ]:
                    _is_rec = (_o == _rec)
                    _oc  = "adv-out-rec" if _is_rec else "adv-out"
                    _vc  = "adv-val-rec" if _is_rec else "adv-val"
                    _pp_s = f"{_pp*100:.0f}%" if _pp is not None else "—"
                    try:
                        _ep_s = f"{float(_ep_raw):.0f}%"
                    except Exception:
                        _ep_s = "—"
                    _adv_body += (
                        f'<div class="adv-row">'
                        f'<span class="{_oc}">{_o}{"&#9733;" if _is_rec else ""}</span>'
                        f'<span class="{_vc}">{_mp*100:.1f}%</span>'
                        f'<span class="adv-val">{_pp_s}</span>'
                        f'<span class="adv-val">{_ep_s}</span>'
                        f'</div>'
                    )

                _meta_lines = []
                if _odds_src:
                    _meta_lines.append(f"Odds: {_odds_src}")
                if _fix_id:
                    _meta_lines.append(f"AF: {_fix_id}")
                if _meta_lines:
                    _adv_body += f'<div class="adv-meta">{"&nbsp;&nbsp;·&nbsp;&nbsp;".join(_meta_lines)}</div>'

                st.markdown(f'<div>{_adv_body}</div>', unsafe_allow_html=True)
