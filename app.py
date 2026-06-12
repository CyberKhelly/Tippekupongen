import streamlit as st
import streamlit.components.v1 as components

from datetime import datetime as _dt

from models.match import Match
from analysis.probability import process_match
from analysis.model import run_model
from analysis.classifier import classify_match
from analysis.optimizer import optimize_coupon
from analysis.classifier import classification_label
from analysis.strategy import STRATEGIES, DEFAULT_STRATEGY
from analysis.pool_value import (
    compute_value_index, compute_p_win,
    compute_pool_value_ratio, simulate_payout,
)
from data.loader import load_coupons

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

# ── Constants ──────────────────────────────────────────────────────────────────
COUPONS = load_coupons()

COUPON_KEYS = list(COUPONS.keys())

_SHORT_LABEL_MAP = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
SHORT_LABELS = {k: _SHORT_LABEL_MAP.get(k, k.capitalize()) for k in COUPON_KEYS}

_NO_DAYS   = ["Man.", "Tir.", "Ons.", "Tor.", "Fre.", "Lør.", "Søn."]
_NO_MONTHS = ["", "jan.", "feb.", "mar.", "apr.", "mai", "jun.",
              "jul.", "aug.", "sep.", "okt.", "nov.", "des."]

def _fmt_deadline(iso: str) -> str:
    try:
        d = _dt.fromisoformat(iso)
        return f"{_NO_DAYS[d.weekday()]} {d.day}. {_NO_MONTHS[d.month]} · {d.strftime('%H:%M')}"
    except Exception:
        return iso

DEADLINES     = {k: _fmt_deadline(v["deadline"]) for k, v in COUPONS.items()}
BUDGET_OPTS   = [32, 96, 192, 384]
BUDGET_LABELS = {32: "Enkel", 96: "Balansert", 192: "Anbefalt", 384: "Høy dekning"}
BUDGET_ROWS   = {32: 32, 96: 96, 192: 192, 384: 384}

_iso        = _dt.now().isocalendar()
_WEEK_LABEL = f"Uke {_iso.week} · {_iso.year}"

_STRATEGY_KEYS   = ["safe", "balanced", "value", "jackpot"]
_STRATEGY_LABELS = {
    "safe":     "Safe",
    "balanced": "Balansert",
    "value":    "Verdi",
    "jackpot":  "Jackpot",
}
_STRATEGY_COLORS = {          # badge colours for the EV panel
    "safe":     ("#1a3a6e", "#5096cc"),
    "balanced": ("#1a2e00", "#f5c518"),
    "value":    ("#0c2a14", "#3aaa78"),
    "jackpot":  ("#2a0c0c", "#e07a5f"),
}
_STRATEGY_NARRATIVES = {
    "safe":     "Safe ignorerer folkemening — maksimerer 12/12-sjansen, men gir lavest forventet utdeling.",
    "balanced": "Balansert bruker mild crowd-justering — god balanse mellom sjanse og poolunikhet.",
    "value":    "Verdi lar crowd-avvik (CDS) styre halvdekk — noe lavere 12/12-sjanse, høyere forventet utdeling.",
    "jackpot":  "Jackpot maksimerer PVR — lavest 12/12-sjanse, men høyest forventet utdeling ved gevinst.",
}

# ── Session state defaults ─────────────────────────────────────────────────────
if "coupon_key" not in st.session_state:
    st.session_state.coupon_key = COUPON_KEYS[0]
if "budget" not in st.session_state:
    st.session_state.budget = 192
if "strategy" not in st.session_state:
    st.session_state.strategy = DEFAULT_STRATEGY
if "omsetning" not in st.session_state:
    st.session_state.omsetning = None
if "_om_raw" not in st.session_state:
    st.session_state._om_raw = 0

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── App shell ──────────────────────────────────────────────────── */
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] {
    background-color: #0b1623 !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
.block-container {
    max-width: 1320px !important;
    margin: 0 auto !important;
    padding-top: 2.5rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    padding-bottom: 3rem !important;
}

/* ── Column layout ───────────────────────────────────────── */
[data-testid="stHorizontalBlock"] {
    gap: 1.5rem !important;
    align-items: flex-start !important;
}
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 5px !important;
    align-items: stretch !important;
}
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    width: 0 !important;
}
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="stButton"] {
    width: 100% !important;
    display: block !important;
}
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] button {
    min-width: 0 !important;
    width: 100% !important;
    white-space: nowrap !important;
    font-size: 0.8rem !important;
}

/* ── Logo ────────────────────────────────────────────────── */
.logo-lockup { display:flex; align-items:center; gap:14px; }
.logo-mark {
    width:48px; height:48px; border-radius:50%;
    background: radial-gradient(circle at 36% 30%, #1e3d7c 0%, #07101e 100%);
    border: 2.5px solid #f5c518;
    display:flex; align-items:center; justify-content:center;
    flex-shrink:0; overflow:hidden;
    box-shadow: 0 0 24px rgba(245,197,24,0.22), 0 4px 16px rgba(0,0,0,0.65),
                inset 0 1px 0 rgba(255,255,255,0.09);
}
.app-wordmark { font-size:1.6rem; font-weight:900; color:#fff; letter-spacing:-0.3px; line-height:1.05; }
.app-wordmark .q { color:#f5c518; }
.app-meta-date { font-size:0.78rem; color:#5a7a96; font-weight:500; white-space:nowrap; padding-top:4px; }
.app-subtitle { font-size:0.65rem; color:#2e4a64; margin-top:2px; }
.app-header-row {
    display:flex; justify-content:space-between; align-items:center;
    padding-bottom:1rem; margin-bottom:1rem;
    border-bottom:1px solid rgba(255,255,255,0.05);
}

/* ── Control bar ─────────────────────────────────────────── */
.control-bar {
    display:flex; align-items:center; gap:1.5rem;
    padding:0.6rem 1rem; margin-bottom:1.25rem;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.05);
    border-radius:8px;
}
.section-label {
    font-size:0.6rem; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.8px;
    margin-bottom:0.35rem; margin-top:0.85rem;
}
.deadline-text { font-size:0.7rem; color:#2e4a64; margin-top:3px; }
.budget-row { display:flex; gap:0; margin-top:2px; }
.budget-sublabel {
    flex:1; font-size:0.6rem; color:#2e4a64;
    text-align:center; padding:1px 0;
}

/* ── Buttons ─────────────────────────────────────────────── */
[data-testid="stButton"] > button[kind="primary"] {
    background:#f5c518 !important; color:#0b1623 !important;
    border:2px solid #f5c518 !important; font-weight:700 !important;
    border-radius:6px !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background:#f7d045 !important;
    box-shadow:0 0 14px rgba(245,197,24,.28) !important;
}
[data-testid="stButton"] > button[kind="secondary"] {
    background:rgba(255,255,255,0.04) !important; color:#c8ddf0 !important;
    border:1px solid rgba(255,255,255,0.07) !important;
    border-radius:6px !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover {
    background:rgba(255,255,255,0.09) !important;
}

/* ── Strategy cards ──────────────────────────────────────── */
.strat-section { margin-bottom:1.5rem; }
.strat-card-wrap {
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px;
    padding:12px 10px 10px;
    background:rgba(255,255,255,0.02);
    transition:border-color 0.15s;
    margin-bottom:0.25rem;
    min-height:140px;
    position:relative;
}
.strat-card-wrap.active {
    border:1.5px solid #f5c518;
    background:rgba(245,197,24,0.06);
    box-shadow:0 0 18px rgba(245,197,24,0.10);
}
.strat-card-wrap:hover { border-color:rgba(255,255,255,0.12); }
.strat-rec-badge {
    font-size:8px; font-weight:700; color:#f5c518;
    text-transform:uppercase; letter-spacing:0.8px;
    margin-bottom:4px;
}
.strat-card-metrics {
    margin-top:8px;
    font-family:'Segoe UI',system-ui,Arial,sans-serif;
    font-size:11px;
}
.strat-card-metrics .m-row { display:flex; justify-content:space-between; margin-bottom:3px; }
.strat-card-metrics .m-lbl { color:#3a5a78; font-size:9px; text-transform:uppercase; letter-spacing:0.5px; }
.strat-card-metrics .m-val { color:#c8ddf0; font-weight:600; font-size:11px; }
.strat-card-metrics .m-val.active { color:#f5c518; }
.strat-card-metrics .m-val.green  { color:#3aaa78; }
.strat-card-metrics .m-val.red    { color:#e07a5f; }

/* ── KPI section ─────────────────────────────────────────── */
.kpi-strip {
    display:flex; gap:12px; margin-bottom:0.5rem;
}
.kpi-card {
    flex:1; padding:16px 18px 14px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.06);
    border-radius:10px;
    display:flex; flex-direction:column; gap:4px;
}
.kpi-val {
    font-size:1.5rem; font-weight:800; color:#e0eaf4;
    letter-spacing:-0.5px; line-height:1.1;
    font-family:'Segoe UI',system-ui,Arial,sans-serif;
}
.kpi-lbl {
    font-size:10px; font-weight:700; color:#3a5a78;
    text-transform:uppercase; letter-spacing:1px;
}
.kpi-sub { font-size:10px; color:#2e4a64; }
.kpi-secondary {
    display:flex; gap:8px; margin-bottom:1.25rem;
    flex-wrap:wrap;
}
.kpi-chip {
    font-size:10px; color:#5a7a96; font-weight:500;
    padding:4px 10px;
    background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.05);
    border-radius:20px;
}

/* ── Payout bar ──────────────────────────────────────────── */
.pay-section {
    padding:18px 20px 16px;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.05);
    border-radius:10px;
    margin-bottom:1.5rem;
}
.pay-header-row {
    display:flex; justify-content:space-between; align-items:center;
    margin-bottom:14px;
}
.pay-title { font-size:10px; font-weight:700; color:#3a5a78; text-transform:uppercase; letter-spacing:1px; }
.pay-om-label { font-size:10px; color:#2e4a64; }
.pay-bar-outer {
    position:relative; height:8px;
    background:rgba(255,255,255,0.05); border-radius:4px;
    margin-bottom:28px;
}
.pay-bar-range {
    position:absolute; top:0; height:8px;
    background:rgba(200,220,240,0.15); border-radius:4px;
}
.pay-bar-median {
    position:absolute; top:0; height:8px;
    background:#f5c518; border-radius:4px; width:6px;
    box-shadow:0 0 8px rgba(245,197,24,0.5);
}
.pay-tick {
    position:absolute; top:14px;
    display:flex; flex-direction:column; align-items:center;
    transform:translateX(-50%);
}
.pay-tick-val { font-size:9px; font-weight:700; color:#c8ddf0; }
.pay-tick-lbl { font-size:8px; color:#3a5a78; margin-top:1px; }
.pay-tick-lbl.gold { color:#f5c518; font-weight:700; }
.pay-meta { font-size:9px; color:#3a5a78; margin-top:6px; line-height:1.5; }
.pay-meta .green { color:#3aaa78; }
.pay-strat-note { font-size:9px; color:#3a5a78; margin-top:4px; font-style:italic; }
.pay-warn { font-size:8px; color:#2e4a64; margin-top:6px; padding:5px 8px; background:rgba(0,0,0,0.2); border-radius:4px; }
.pay-placeholder {
    text-align:center; padding:20px;
    font-size:11px; color:#2e4a64;
}

/* ── Coupon v2 ───────────────────────────────────────────── */
.panel-title {
    font-size:9px; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    padding-bottom:8px; margin-bottom:8px;
    border-bottom:1px solid rgba(255,255,255,0.06);
}
.cpn-meta-box {
    padding:14px 16px;
    background:rgba(255,255,255,0.02);
    border:1px solid rgba(255,255,255,0.05);
    border-radius:8px;
    margin-bottom:12px;
}
.cpn-meta-row { display:flex; justify-content:space-between; margin-bottom:6px; }
.cpn-meta-lbl { font-size:10px; color:#3a5a78; text-transform:uppercase; letter-spacing:0.5px; }
.cpn-meta-val { font-size:10px; color:#c8ddf0; font-weight:600; }
.cpn-pvr-badge {
    display:inline-block; padding:3px 9px; border-radius:12px;
    font-size:9px; font-weight:700;
}

/* ── Analysis table ──────────────────────────────────────── */
.analysis-section-label {
    font-size:9px; font-weight:700; color:#2e4a64;
    text-transform:uppercase; letter-spacing:1.5px;
    padding-bottom:8px; margin-top:1rem; margin-bottom:0.5rem;
    border-bottom:1px solid rgba(255,255,255,0.06);
}
.footnote { font-size:9px; color:#2e4a64; margin-top:6px; }

/* ── Advanced expander ───────────────────────────────────── */
[data-testid="stExpander"] {
    border:1px solid rgba(255,255,255,0.05) !important;
    border-radius:8px !important;
    background:rgba(255,255,255,0.01) !important;
}
[data-testid="stExpander"] summary {
    font-size:10px !important; font-weight:700 !important;
    color:#3a5a78 !important; text-transform:uppercase !important;
    letter-spacing:1px !important;
}

/* ── Misc ────────────────────────────────────────────────── */
iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _val_pp_for_pick(m, rec: str):
    """Returns (value_pp_float, has_public) for the recommended pick."""
    field = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
    return field, m.has_public_tips

def _vi_for_pick(m, rec: str):
    """Returns VI float or None for the recommended pick."""
    from analysis.pool_value import compute_value_index
    prob = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec)
    pub  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
    return compute_value_index(prob or 0, pub)

def load_matches(coupon_key: str) -> list[Match]:
    # Fetch enrichment data (form, standings, NT tips) keyed by match_number.
    # Fails silently so the app always works even without a DB or enrichment.
    enrichment_map: dict[int, dict] = {}
    try:
        from db.schema import init_db
        from db.enrichment import get_coupon_enrichment
        init_db()
        coupon_id = f"{coupon_key}-{_iso.week:02d}-{_iso.year}"
        for row in get_coupon_enrichment(coupon_id):
            enrichment_map[row["match_number"]] = row
    except Exception:
        pass

    matches = []
    for i, row in enumerate(COUPONS[coupon_key]["matches"], 1):
        home, away, oh, ou, ob = row[:5]
        src = row[5] if len(row) > 5 else ""
        m = Match(number=i, home_team=home, away_team=away,
                  odds_h=oh, odds_u=ou, odds_b=ob, odds_source=src)
        process_match(m)
        run_model(m, enrichment_map.get(i))   # Phase 5: unified model
        classify_match(m)
        matches.append(m)
    return matches


def compute_pool_value_score(matches: list[Match], picks: dict) -> float | None:
    """
    Average pp advantage over the public for the actual single picks in the coupon.

    Only single-pick matches contribute — halvdekk and heldekk are excluded because
    covering multiple outcomes dilutes any pool-value signal. This makes the metric
    sensitive to strategy (strategy controls which matches are singles).
    """
    values = []
    for m in matches:
        if not m.has_public_tips:
            continue
        p = picks.get(m.number, [])
        if len(p) != 1:
            continue
        v = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(p[0])
        if v is not None:
            values.append(v)
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def render_coupon_card_v2(
    coupon_key: str,
    matches: list[Match],
    picks: dict,
    total_rows: int,
    budget: float,
) -> None:
    """Redesigned coupon card with rich match rows: pick, confidence, value pp, VI."""
    from analysis.pool_value import compute_value_index as _cvi

    _cov_labels = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}
    _strat_name  = _STRATEGY_LABELS.get(st.session_state.strategy, "")
    _coupon_name = SHORT_LABELS.get(coupon_key, coupon_key.capitalize())
    _iso         = _dt.now().isocalendar()

    # Build rows HTML
    rows_html = ""
    for m in matches:
        n_picks  = len(picks[m.number])
        cov_lbl  = _cov_labels[n_picks]
        rec      = m.recommendation or ""

        # Confidence
        conf_val = round(m.confidence * 100, 0)
        conf_str = f"{conf_val:.0f}%"

        # Value pp for recommended pick
        val_field = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        if val_field is not None and m.has_public_tips:
            vpp = val_field * 100
            val_str = f"{vpp:+.1f}pp"
            val_col = "#3aaa78" if vpp > 0 else "#e07a5f"
        else:
            val_str = "—"
            val_col = "#2e4a64"

        # VI for recommended pick
        prob = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec)
        pub  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi   = _cvi(prob or 0, pub)
        if vi is not None:
            vi_str = f"{vi:.2f}×"
            vi_col = "#3aaa78" if vi >= 1.25 else "#74cc9a" if vi >= 1.0 else "#e0956a" if vi >= 0.80 else "#e07a5f"
        else:
            vi_str = "—"
            vi_col = "#2e4a64"

        # Coverage color
        cov_col = {"Single": "#5096cc", "Halvdekk": "#c8960e", "Heldekkende": "#be5050"}[cov_lbl]

        rows_html += f"""
<tr>
  <td style="padding:7px 8px 7px 10px;color:#2e4a64;font-size:10px;text-align:center;white-space:nowrap;border-bottom:1px solid rgba(255,255,255,0.03);">{m.number}</td>
  <td style="padding:7px 10px;color:#c8ddf0;font-size:11px;white-space:nowrap;border-bottom:1px solid rgba(255,255,255,0.03);max-width:160px;overflow:hidden;text-overflow:ellipsis;">{m.label}</td>
  <td style="padding:7px 10px;text-align:center;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap;">
    <span style="font-size:11px;font-weight:800;color:#f5c518;">{"/".join(picks[m.number])}</span>
    {"<span style='font-size:9px;color:#c8960e;margin-left:3px;'>&#9680;</span>" if n_picks == 2 else ""}
    {"<span style='font-size:9px;color:#be5050;margin-left:3px;'>&#9679;</span>" if n_picks == 3 else ""}
    <div style="font-size:8px;color:{cov_col};margin-top:1px;">{cov_lbl}</div>
  </td>
  <td style="padding:7px 10px;text-align:center;font-size:10px;color:#6a90b0;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap;">{conf_str}</td>
  <td style="padding:7px 10px;text-align:right;font-size:10px;color:{val_col};font-weight:600;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap;">{val_str}</td>
  <td style="padding:7px 10px;text-align:right;font-size:10px;color:{vi_col};font-weight:700;border-bottom:1px solid rgba(255,255,255,0.03);white-space:nowrap;">{vi_str}</td>
</tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
body{{margin:0;padding:0;background:transparent;font-family:'Segoe UI',system-ui,Arial,sans-serif;}}
table{{width:100%;border-collapse:collapse;}}
thead th{{font-size:8px;font-weight:700;color:#2e4a64;text-transform:uppercase;letter-spacing:1px;
    padding:6px 10px 6px;border-bottom:1px solid rgba(255,255,255,0.07);background:rgba(255,255,255,0.03);white-space:nowrap;}}
.hdr-card{{background:linear-gradient(135deg,#0d2050 0%,#1a3a6e 100%);
    padding:12px 14px 10px;border-radius:8px 8px 0 0;margin-bottom:0;}}
.hdr-title{{font-size:11px;font-weight:900;color:#e0eaf4;letter-spacing:1px;text-transform:uppercase;}}
.hdr-sub{{font-size:9px;color:#5a7a96;margin-top:2px;}}
.card-wrap{{border:1px solid rgba(255,255,255,0.07);border-radius:8px;overflow:hidden;
    background:rgba(255,255,255,0.02);}}
</style>
</head><body>
<div class="card-wrap">
<div class="hdr-card">
  <div class="hdr-title">TIPPEQUPONGEN</div>
  <div class="hdr-sub">{_strat_name} &middot; {_coupon_name} &middot; Uke {_iso.week}</div>
</div>
<table>
<thead>
<tr>
  <th style="text-align:center;">#</th>
  <th style="text-align:left;">Kamp</th>
  <th style="text-align:center;">Pick</th>
  <th style="text-align:center;">Konf.</th>
  <th style="text-align:right;">Verdi</th>
  <th style="text-align:right;">VI</th>
</tr>
</thead>
<tbody>{rows_html}</tbody>
</table>
</div>
</body></html>"""

    n_matches = len(matches)
    height = 56 + 28 + n_matches * 52 + 10  # header + col-head + rows + padding
    components.html(html, height=height, scrolling=False)


def render_analysis_table_v2(matches: list[Match], picks: dict) -> None:
    """Analysis table with probability bars."""
    from analysis.pool_value import compute_value_index as _cvi

    _cov = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}
    _conf_tiers = [
        (60, "#0c2a14", "#3ecf7a"),
        (52, "#122212", "#74c472"),
        (45, "#261c04", "#c8960e"),
        ( 0, "#260c0c", "#be5050"),
    ]
    _cov_colors = {
        "Single":      ("#0c1e34", "#5096cc"),
        "Halvdekk":    ("#261c04", "#c8960e"),
        "Heldekkende": ("#260c0c", "#be5050"),
    }
    _badge = "font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;white-space:nowrap;"

    def conf_colors(v):
        for thr, bg, fg in _conf_tiers:
            if v >= thr:
                return bg, fg
        return _conf_tiers[-1][1], _conf_tiers[-1][2]

    _th = ("font-size:9px;font-weight:700;color:#2e4a64;text-transform:uppercase;"
           "letter-spacing:1.3px;border-bottom:1px solid rgba(255,255,255,0.07);"
           "white-space:nowrap;background:rgba(255,255,255,0.04);padding:8px 9px;")

    thead = (
        f'<tr>'
        f'<th style="{_th}text-align:center;">#</th>'
        f'<th style="{_th}text-align:left;">Kamp</th>'
        f'<th style="{_th}text-align:left;min-width:160px;">Sannsynlighet</th>'
        f'<th style="{_th}text-align:center;">Tips</th>'
        f'<th style="{_th}text-align:center;">Konf.</th>'
        f'<th style="{_th}text-align:center;">Dek.</th>'
        f'<th style="{_th}text-align:right;">VI</th>'
        f'</tr>'
    )

    _td = "padding:5px 9px;font-size:11px;"

    # Bar colors
    H_COL = "#5096cc"
    U_COL = "#6a7a88"
    B_COL = "#c8960e"
    TRACK = "rgba(255,255,255,0.05)"

    def bar_html(label: str, pct: float, color: str) -> str:
        w = min(100, max(0, round(pct)))
        return (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">'
            f'<div style="width:14px;font-size:9px;color:#3a5a78;text-align:right;">{label}</div>'
            f'<div style="flex:1;height:6px;background:{TRACK};border-radius:3px;overflow:hidden;">'
            f'<div style="width:{w}%;height:6px;background:{color};border-radius:3px;"></div>'
            f'</div>'
            f'<div style="width:32px;font-size:9px;color:#6a90b0;text-align:right;">{pct:.0f}%</div>'
            f'</div>'
        )

    rows_html = ""
    for i, m in enumerate(matches):
        n        = len(picks[m.number])
        cov_lbl  = _cov[n]
        conf_val = round(m.confidence * 100, 1)
        cbg, cfg = conf_colors(conf_val)
        vbg, vfg = _cov_colors[cov_lbl]
        row_bg   = "rgba(255,255,255,0.015)" if i % 2 == 0 else "transparent"

        # VI
        rec = m.recommendation or ""
        prob = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec)
        pub  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi   = _cvi(prob or 0, pub)
        if vi is not None:
            vi_col = "#3aaa78" if vi >= 1.25 else "#74cc9a" if vi >= 1.0 else "#e0956a" if vi >= 0.80 else "#e07a5f"
            vi_str = f"{vi:.2f}×"
        else:
            vi_col, vi_str = "#2e4a64", "—"

        bars = (
            bar_html("H", m.prob_h * 100, H_COL) +
            bar_html("U", m.prob_u * 100, U_COL) +
            bar_html("B", m.prob_b * 100, B_COL)
        )

        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="{_td}color:#2e4a64;text-align:center;vertical-align:middle;">{m.number}</td>'
            f'<td style="{_td}color:#c8ddf0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:150px;vertical-align:middle;">{m.label}</td>'
            f'<td style="{_td}vertical-align:middle;padding:8px 9px 8px;">{bars}</td>'
            f'<td style="{_td}text-align:center;font-weight:800;color:#f5c518;vertical-align:middle;">{m.recommendation}</td>'
            f'<td style="{_td}text-align:center;vertical-align:middle;"><span style="{_badge}background:{cbg};color:{cfg};">{conf_val:.0f}%</span></td>'
            f'<td style="{_td}text-align:center;vertical-align:middle;"><span style="{_badge}background:{vbg};color:{vfg};">{cov_lbl}</span></td>'
            f'<td style="{_td}text-align:right;font-weight:700;color:{vi_col};font-size:10px;vertical-align:middle;">{vi_str}</td>'
            f'</tr>'
        )

    html = (
        '<div style="overflow-x:auto;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">'
        '<table style="width:100%;border-collapse:collapse;font-family:\'Segoe UI\',system-ui,Arial,sans-serif;">'
        f'<thead>{thead}</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-header-row">
  <div class="logo-lockup">
    <div class="logo-mark">
      <svg viewBox="0 0 32 32" width="26" height="26">
        <circle cx="16" cy="16" r="13" fill="none" stroke="#f5c518" stroke-width="1.5" opacity="0.45"/>
        <path d="M 16 9 L 22.7 13.8 L 20.1 21.7 L 11.9 21.7 L 9.3 13.8 Z" fill="rgba(245,197,24,0.13)" stroke="#f5c518" stroke-width="1.3"/>
        <line x1="16"  y1="9"    x2="16"  y2="3"    stroke="#f5c518" stroke-width="1" opacity="0.5"/>
        <line x1="22.7" y1="13.8" x2="28.4" y2="12"   stroke="#f5c518" stroke-width="1" opacity="0.5"/>
        <line x1="20.1" y1="21.7" x2="23.6" y2="26.5" stroke="#f5c518" stroke-width="1" opacity="0.5"/>
        <line x1="11.9" y1="21.7" x2="8.4"  y2="26.5" stroke="#f5c518" stroke-width="1" opacity="0.5"/>
        <line x1="9.3"  y1="13.8" x2="3.6"  y2="12"   stroke="#f5c518" stroke-width="1" opacity="0.5"/>
      </svg>
    </div>
    <div>
      <div class="app-wordmark">Tippe<span class="q">Q</span>pongen</div>
      <div class="app-subtitle">Basert på estimerte odds · oppdateres ukentlig</div>
    </div>
  </div>
  <div class="app-meta-date">{_WEEK_LABEL}</div>
</div>
""", unsafe_allow_html=True)

# ── Coupon selector ───────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Kupong</div>', unsafe_allow_html=True)
t1, t2, t3 = st.columns(3)
for col, key in zip([t1, t2, t3], COUPON_KEYS):
    with col:
        active = st.session_state.coupon_key == key
        if st.button(SHORT_LABELS[key], key=f"tab_{key}",
                     use_container_width=True,
                     type="primary" if active else "secondary"):
            st.session_state.coupon_key = key
            st.rerun()

coupon_key = st.session_state.coupon_key
st.markdown(
    f'<div class="deadline-text">&#9679; Frist: {DEADLINES[coupon_key]} &middot; 12 kamper</div>',
    unsafe_allow_html=True,
)

st.markdown('<div class="section-label">Budsjett</div>', unsafe_allow_html=True)
b1, b2, b3, b4 = st.columns(4)
for col, amt in zip([b1, b2, b3, b4], BUDGET_OPTS):
    with col:
        active = st.session_state.budget == amt
        if st.button(f"{amt} NOK", key=f"budget_{amt}",
                     use_container_width=True,
                     type="primary" if active else "secondary"):
            st.session_state.budget = amt
            st.rerun()

st.markdown(
    '<div class="budget-row">'
    + "".join(
        f'<div class="budget-sublabel"><strong>{BUDGET_LABELS[amt]}</strong><br>{BUDGET_ROWS[amt]} rek.</div>'
        for amt in BUDGET_OPTS
    )
    + "</div>",
    unsafe_allow_html=True,
)

budget   = st.session_state.budget
strategy = st.session_state.strategy

# ── Compute block (hoisted) ────────────────────────────────────────────────────
matches = load_matches(coupon_key)
picks, total_rows = optimize_coupon(matches, float(budget), strategy=strategy)
pvs = compute_pool_value_score(matches, picks)
p_win    = compute_p_win(matches, picks)
pv_ratio = compute_pool_value_ratio(matches, picks)

_omsetning = st.session_state.omsetning
_sim = None
if _omsetning and _omsetning > 0:
    _sim = simulate_payout(matches, picks, total_rows, float(_omsetning))

# Strategy comparison data (all 4 strategies)
_cmp_data: list[tuple] = []
for _sk in _STRATEGY_KEYS:
    _sp, _sr = optimize_coupon(matches, float(budget), strategy=_sk)
    _cmp_pw  = compute_p_win(matches, _sp)
    _cmp_pvr = compute_pool_value_ratio(matches, _sp)
    _cmp_med: int | None = None
    if _omsetning and _omsetning > 0:
        _csim = simulate_payout(matches, _sp, _sr, float(_omsetning), n_sims=10_000)
        if _csim.get("n_winning_sims", 0) > 0:
            _cmp_med = _csim["median"]
    _cmp_data.append((_sk, _cmp_pw, _cmp_pvr, _cmp_med))

# ── 1. Strategy cards ──────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Velg strategi</div>', unsafe_allow_html=True)
sc1, sc2, sc3, sc4 = st.columns(4)
for col, (_sk, _cpw, _cpvr, _cmed) in zip([sc1, sc2, sc3, sc4], _cmp_data):
    with col:
        is_active = strategy == _sk
        is_rec    = _sk == "balanced"
        card_cls  = "strat-card-wrap active" if is_active else "strat-card-wrap"
        pw_str    = f"{_cpw*100:.1f}%"
        pvr_str   = f"{_cpvr:.2f}&times;" if _cpvr else "&#8212;"
        med_str   = f"{_cmed:,} kr" if _cmed else "&#8212;"
        pvr_cls   = "green" if (_cpvr or 0) >= 1.0 else "red"
        act_cls   = "active" if is_active else ""
        rec_html  = '<div class="strat-rec-badge">&#9733; Anbefalt</div>' if is_rec else ""
        st.markdown(f'<div class="{card_cls}">{rec_html}</div>', unsafe_allow_html=True)
        if st.button(_STRATEGY_LABELS[_sk], key=f"strategy_{_sk}",
                     use_container_width=True,
                     type="primary" if is_active else "secondary"):
            st.session_state.strategy = _sk
            st.rerun()
        st.markdown(f"""
<div class="strat-card-metrics">
  <div class="m-row"><span class="m-lbl">P(12/12)</span><span class="m-val {act_cls}">{pw_str}</span></div>
  <div class="m-row"><span class="m-lbl">PVR</span><span class="m-val {pvr_cls}">{pvr_str}</span></div>
  <div class="m-row"><span class="m-lbl">Median</span><span class="m-val">{med_str}</span></div>
</div>""", unsafe_allow_html=True)

# ── 2. KPI section ─────────────────────────────────────────────────────────────
_pwin_col = "#3aaa78" if p_win >= 0.05 else "#c8960e" if p_win >= 0.01 else "#e07a5f"
_pvr_col  = "#3aaa78" if (pv_ratio or 0) >= 1.0 else "#e07a5f"
_pwin_str = f"{p_win*100:.2f}%"
_pvr_str_kpi  = f"{pv_ratio:.2f}&times;" if pv_ratio else "&#8212;"
_pvr_sub  = "&#9679; positiv pool-edge" if (pv_ratio or 0) >= 1.0 else "&#9679; under markedet"
_med_str  = f"{_sim['median']:,} kr" if _sim and _sim.get("n_winning_sims", 0) > 0 else "&#8212;"
_p90_str  = f"{_sim['p90']:,} kr"   if _sim and _sim.get("n_winning_sims", 0) > 0 else "&#8212;"
_med_sub  = "ved 12/12" if _sim else "Legg inn omsetning"
_p90_sub  = "90% scenario" if _sim else "Legg inn omsetning"

_n_val_picks = sum(
    1 for m in matches
    if m.has_public_tips and m.recommendation and
    ({"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(m.recommendation) or 0) > 0
)

_pvs_str = f"{pvs:+.1f}pp" if pvs is not None else "&#8212;"
_ew_str  = f"~{_sim['e_winners']:,}" if _sim and _sim.get("n_winning_sims", 0) > 0 else "&#8212;"

st.markdown(f"""
<div class="kpi-strip">
  <div class="kpi-card">
    <div class="kpi-val" style="color:{_pwin_col};">{_pwin_str}</div>
    <div class="kpi-lbl">P(12/12)</div>
    <div class="kpi-sub">Sjanse for 12 rette</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val" style="color:#f5c518;">{_med_str}</div>
    <div class="kpi-lbl">Median utdeling</div>
    <div class="kpi-sub">{_med_sub}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val" style="color:{_pvr_col};">{_pvr_str_kpi}</div>
    <div class="kpi-lbl">Poolverdi ratio</div>
    <div class="kpi-sub">{_pvr_sub}</div>
  </div>
  <div class="kpi-card">
    <div class="kpi-val">{_p90_str}</div>
    <div class="kpi-lbl">P90 utdeling</div>
    <div class="kpi-sub">{_p90_sub}</div>
  </div>
</div>
<div class="kpi-secondary">
  <span class="kpi-chip">Poolverdi: {_pvs_str}</span>
  <span class="kpi-chip">Verdivalg: {_n_val_picks} kamper</span>
  <span class="kpi-chip">E[vinnere]: {_ew_str}</span>
</div>
""", unsafe_allow_html=True)

# ── 3. Payout section ──────────────────────────────────────────────────────────
def _on_om_change():
    v = st.session_state._om_raw
    st.session_state.omsetning = int(v) if v and v > 0 else None

_om_display = f"{int(_omsetning):,} NOK" if _omsetning else "ikke satt"
st.markdown(
    f'<div class="pay-section"><div class="pay-header-row">'
    f'<div class="pay-title">Estimert utdeling ved 12/12</div>'
    f'<div class="pay-om-label">Omsetning: {_om_display}</div></div>',
    unsafe_allow_html=True,
)

if _sim and _sim.get("n_winning_sims", 0) > 0:
    _vmin = _sim["min"]
    _vmax = _sim.get("p99", _sim["max"])
    if _vmax <= _vmin:
        _vmax = _vmin + 1

    def _bar_pct(v):
        return max(0.0, min(98.0, (v - _vmin) / (_vmax - _vmin) * 100))

    _ticks = [
        (_bar_pct(_sim["min"]),    f"{_sim['min']//1000}k",    "Min",    False),
        (_bar_pct(_sim["p10"]),    f"{_sim['p10']//1000}k",    "P10",    False),
        (_bar_pct(_sim["median"]), f"{_sim['median']//1000}k", "Median", True),
        (_bar_pct(_sim["p90"]),    f"{_sim['p90']//1000}k",    "P90",    False),
        (_bar_pct(_vmax),          f"{_vmax//1000}k",          "P99",    False),
    ]
    _range_l = _bar_pct(_sim["p10"])
    _range_w = _bar_pct(_sim["p90"]) - _range_l
    _med_pos = _bar_pct(_sim["median"]) - 0.3

    _tick_html = "".join(
        f'<div class="pay-tick" style="left:{pos:.1f}%;">'
        f'<div class="pay-tick-val">{val}</div>'
        f'<div class="pay-tick-lbl{"" if not gold else " gold"}">{lbl}</div>'
        f'</div>'
        for pos, val, lbl, gold in _ticks
    )

    _ew_pay  = _sim.get("e_winners", 0)
    _ew_pay_s = f"~{_ew_pay:,}" if isinstance(_ew_pay, int) else "&#8212;"
    _strat_note = _STRATEGY_NARRATIVES[strategy]

    st.markdown(f"""
<div class="pay-bar-outer">
  <div class="pay-bar-range" style="left:{_range_l:.1f}%;width:{_range_w:.1f}%;"></div>
  <div class="pay-bar-median" style="left:{_med_pos:.1f}%;"></div>
  {_tick_html}
</div>
<div class="pay-meta">
  E[vinnere]: {_ew_pay_s} rekker deler potten ved gevinst
  {"&nbsp;&middot;&nbsp;<span class='green'>PVR " + f"{pv_ratio:.2f}&times;" + " &rarr; underpopulert pool</span>" if (pv_ratio or 0) >= 1.0 else ""}
</div>
<div class="pay-strat-note">{_strat_note}</div>
<div class="pay-warn">&#9888; Simuleringsestimat &mdash; ikke garantert utbetaling &middot; 50&#8239;000 simuleringer &middot; 52% premieandel &middot; Omsetning {int(_omsetning or 0):,} NOK</div>
""", unsafe_allow_html=True)
else:
    st.markdown(
        '<div class="pay-placeholder">Legg inn omsetning nedenfor for å estimere potensiell utdeling.</div>',
        unsafe_allow_html=True,
    )

st.markdown('</div>', unsafe_allow_html=True)  # close pay-section

st.number_input(
    "Omsetning (NOK)",
    key="_om_raw",
    min_value=0,
    max_value=200_000_000,
    value=int(st.session_state.omsetning or 0),
    step=500_000,
    on_change=_on_om_change,
    help="Finn aktuell omsetning på Norsk Tipping sin nettside.",
    label_visibility="collapsed",
)

st.markdown("<div style='height:0.25rem'></div>", unsafe_allow_html=True)

# ── 4. Coupon + meta ──────────────────────────────────────────────────────────
cpn_col, meta_col = st.columns([7, 4])

with cpn_col:
    st.markdown('<div class="panel-title">Kupong</div>', unsafe_allow_html=True)
    render_coupon_card_v2(coupon_key, matches, picks, total_rows, budget)

with meta_col:
    st.markdown('<div class="panel-title">Kupongoversikt</div>', unsafe_allow_html=True)
    total_cost = total_rows * 2  # 2 NOK per row
    remaining  = float(budget) - total_cost
    rem_clr    = "color:#3aaa78" if remaining >= 0 else "color:#e07a5f"

    n_full = sum(1 for m in matches if len(picks[m.number]) == 3)
    n_half = sum(1 for m in matches if len(picks[m.number]) == 2)
    n_sing = sum(1 for m in matches if len(picks[m.number]) == 1)

    _pvr_badge_bg  = "#0c2a14" if (pv_ratio or 0) >= 1.0 else "#260c0c"
    _pvr_badge_fg  = "#3aaa78" if (pv_ratio or 0) >= 1.0 else "#e07a5f"
    _pvr_badge_str = f"{pv_ratio:.2f}&times;" if pv_ratio else "&#8212;"

    st.markdown(f"""
<div class="cpn-meta-box">
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Rekker</span><span class="cpn-meta-val">{total_rows}</span></div>
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Kostnad</span><span class="cpn-meta-val">{total_cost:.0f} NOK</span></div>
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Rest</span><span class="cpn-meta-val" style="{rem_clr};">{remaining:+.0f} NOK</span></div>
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Heldekkende</span><span class="cpn-meta-val">{n_full}</span></div>
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Halvdekk</span><span class="cpn-meta-val">{n_half}</span></div>
  <div class="cpn-meta-row"><span class="cpn-meta-lbl">Single</span><span class="cpn-meta-val">{n_sing}</span></div>
</div>
<div style="margin-bottom:10px;">
  <span class="kpi-lbl">Poolverdi ratio</span><br>
  <span class="cpn-pvr-badge" style="background:{_pvr_badge_bg};color:{_pvr_badge_fg};margin-top:4px;">{_pvr_badge_str}</span>
</div>
""", unsafe_allow_html=True)

    if (pv_ratio or 0) < 0.85:
        st.markdown(
            '<div style="font-size:9px;background:#261c04;color:#c8960e;padding:6px 10px;border-radius:6px;margin-bottom:10px;">&#9888; Kupongen er nær folkemeningen — vurder Verdi eller Jackpot</div>',
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    if st.button("Lagre kupong", use_container_width=True, type="secondary"):
        from db.schema import init_db as _init_db2
        from db.coupon import get_coupon_matches, get_best_odds
        from db.history import save_prediction

        _init_db2()
        coupon_id = f"{coupon_key}-{_iso.week:02d}-{_iso.year}"
        db_matches = get_coupon_matches(coupon_id)
        fid_map = {r["match_number"]: r["fixture_id"] for r in db_matches}

        saved = 0
        missing = 0
        for m in matches:
            fid = fid_map.get(m.number)
            if not fid:
                missing += 1
                continue
            best = get_best_odds(fid)
            oh = best["odds_h"] if best else None
            ou = best["odds_u"] if best else None
            ob = best["odds_b"] if best else None
            os_ = best["source"] if best else None
            save_prediction(
                coupon_id=coupon_id,
                fixture_id=fid,
                match_number=m.number,
                recommended_pick=m.recommendation,
                picks=picks[m.number],
                confidence=m.confidence,
                implied_prob_h=m.prob_h,
                implied_prob_u=m.prob_u,
                implied_prob_b=m.prob_b,
                odds_h=oh, odds_u=ou, odds_b=ob,
                odds_source=os_,
            )
            saved += 1

        if saved == len(matches):
            st.success(f"Kupong lagret! ({saved} kamper)")
        elif saved > 0:
            st.warning(f"{saved} av {len(matches)} lagret. {missing} kamp(er) mangler fixture_id.")
        else:
            st.error("Kunne ikke lagre: kjør sync.py --seed-only først.")

# ── 5. Analysis table ─────────────────────────────────────────────────────────
st.markdown('<div class="analysis-section-label">Kampanalyse</div>', unsafe_allow_html=True)
render_analysis_table_v2(matches, picks)
st.markdown(
    '<div class="footnote">Konf. = modellens konfidensgrad for anbefalt utfall &middot; '
    'Dek. = dekningstype (&times;1 Single, &times;2 Halvdekk, &times;3 Heldekkende) &middot; '
    'VI = Verdiindeks (modell / folket for valgt utfall)</div>',
    unsafe_allow_html=True,
)

# ── 6. Advanced collapsible ───────────────────────────────────────────────────
with st.expander("Avanserte detaljer — strategisammenligning og diagnostikk"):
    _has_med_col = any(d[3] is not None for d in _cmp_data)

    _cmp_rows_adv = ""
    for _sk, _cpw, _cpvr, _cmed in _cmp_data:
        _is_act = _sk == strategy
        _ac     = " style='color:#e0eaf4;font-weight:700;background:rgba(255,255,255,0.04);'" if _is_act else ""
        _lbl    = ("&#9654; " if _is_act else "  ") + _STRATEGY_LABELS[_sk]
        _pw_s   = f"{_cpw*100:.2f}%"
        _pvr_s  = f"{_cpvr:.2f}&times;" if _cpvr else "&#8212;"
        _pvr_style = ""
        if _is_act and _cpvr:
            _pvr_style = f" style='color:{'#3aaa78' if _cpvr >= 1.0 else '#e07a5f'};'"
        _cmp_rows_adv += (
            f"<tr{_ac}>"
            f"<td style='text-align:left;padding:4px 8px;'>{_lbl}</td>"
            f"<td style='text-align:center;padding:4px 8px;'>{_pw_s}</td>"
            f"<td style='text-align:center;padding:4px 8px;'{_pvr_style}>{_pvr_s}</td>"
        )
        if _has_med_col:
            _med_s = f"{_cmed:,} kr" if _cmed else "&#8212;"
            _cmp_rows_adv += f"<td style='text-align:center;padding:4px 8px;'>{_med_s}</td>"
        _cmp_rows_adv += "</tr>"

    _med_th = "<th style='text-align:center;'>Median *</th>" if _has_med_col else ""
    _cmp_table = f"""
<div style="overflow-x:auto;">
<table style="width:100%;border-collapse:collapse;font-size:11px;font-family:'Segoe UI',system-ui,Arial,sans-serif;">
<thead>
<tr style="font-size:9px;color:#2e4a64;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid rgba(255,255,255,0.07);">
<th style="text-align:left;padding:5px 8px;">Strategi</th>
<th style="text-align:center;padding:5px 8px;">P(12/12)</th>
<th style="text-align:center;padding:5px 8px;">PVR</th>
{_med_th}
</tr>
</thead>
<tbody style="color:#4a6a88;">{_cmp_rows_adv}</tbody>
</table>
</div>"""
    if _has_med_col:
        _cmp_table += '<div style="font-size:8px;color:#2e4a64;margin-top:4px;font-style:italic;">* Median simulert utdeling ved 12/12 &mdash; 10&#8239;000 simuleringer pr. strategi</div>'

    st.markdown(_cmp_table, unsafe_allow_html=True)