import streamlit as st
import streamlit.components.v1 as components

from datetime import datetime as _dt

from models.match import Match
from analysis.probability import process_match
from analysis.model import run_model
from analysis.classifier import classify_match
from analysis.optimizer import optimize_coupon, generate_anchor_coupon, compare_coupons
from analysis.classifier import classification_label
from analysis.strategy import STRATEGIES, DEFAULT_STRATEGY
from analysis.pool_value import (
    compute_value_index, compute_p_win,
    compute_pool_value_ratio, simulate_payout,
)
from data.loader import load_coupons

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
        return f"{_NO_DAYS[d.weekday()]} {d.day}. {_NO_MONTHS[d.month]} kl. {d.strftime('%H:%M')}"
    except Exception:
        return iso

DEADLINES   = {k: _fmt_deadline(v["deadline"]) for k, v in COUPONS.items()}
BUDGET_OPTS = [32, 96, 192, 384]
BUDGET_LABELS = {32: "Minimal", 96: "Moderat", 192: "Anbefalt", 384: "Aggressiv"}

_iso        = _dt.now().isocalendar()
_WEEK_LABEL = f"Uke {_iso.week}"

_STRATEGY_KEYS = ["safe", "balanced", "jackpot"]
_STRATEGY_LABELS = {
    "safe":     "Safe",
    "balanced": "Balansert",
    "jackpot":  "Jackpot",
}
_STRATEGY_DESC = {
    "safe":     "Maks P(12/12). Minst risiko.",
    "balanced": "Balanse sjanse og verdi.",
    "jackpot":  "Maks PVR. Høy potensiell gevinst.",
}
_STRATEGY_NARRATIVES = {
    "safe":     "Safe ignorerer folkemening — maksimerer 12/12-sjansen.",
    "balanced": "Balansert bruker mild crowd-justering — god balanse mellom sjanse og poolunikhet.",
    "jackpot":  "Jackpot maksimerer PVR — lavest 12/12-sjanse, men høyest forventet utdeling ved gevinst.",
}

# ── Session state ──────────────────────────────────────────────────────────────
if "coupon_key" not in st.session_state:
    st.session_state.coupon_key = COUPON_KEYS[0]
if "budget" not in st.session_state:
    st.session_state.budget = 192
if "strategy" not in st.session_state or st.session_state.strategy not in _STRATEGY_KEYS:
    st.session_state.strategy = DEFAULT_STRATEGY
if "omsetning" not in st.session_state:
    st.session_state.omsetning = None
if "_om_raw" not in st.session_state:
    st.session_state._om_raw = 0

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ── Reset & shell ───────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
.stApp {
    background:
        radial-gradient(ellipse at 18% 0%, rgba(18,50,120,0.55) 0%, transparent 55%),
        radial-gradient(ellipse at 85% 95%, rgba(10,25,70,0.35) 0%, transparent 50%),
        #07111e;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
.block-container {
    max-width: 1200px !important;
    margin: 0 auto !important;
    padding-top: 2.5rem !important;
    padding-left: 2.5rem !important;
    padding-right: 2.5rem !important;
    padding-bottom: 5rem !important;
}
[data-testid="stSidebar"] { display: none !important; }

/* ── Streamlit widget overrides ──────────────────────────────────────────── */
[data-testid="stHorizontalBlock"] {
    gap: 0.75rem !important;
    align-items: flex-start !important;
}
/* Button reset */
[data-testid="stButton"] > button {
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif !important;
    font-weight: 500 !important;
    font-size: 0.8rem !important;
    border-radius: 6px !important;
    transition: all 0.12s ease !important;
    letter-spacing: 0 !important;
}
[data-testid="stButton"] > button[kind="primary"] {
    background: #f5c518 !important;
    color: #08111c !important;
    border: none !important;
    font-weight: 700 !important;
}
[data-testid="stButton"] > button[kind="primary"]:hover {
    background: #f7d045 !important;
    box-shadow: 0 0 0 3px rgba(245,197,24,0.2) !important;
}
[data-testid="stButton"] > button[kind="secondary"] {
    background: transparent !important;
    color: #8aabb8 !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.04) !important;
    color: #c8ddf0 !important;
    border-color: rgba(255,255,255,0.16) !important;
}
/* Expander */
[data-testid="stExpander"] {
    border: none !important;
    background: transparent !important;
}
[data-testid="stExpander"] > details {
    border: none !important;
    background: transparent !important;
}
[data-testid="stExpander"] summary {
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    color: #2e4a64 !important;
    letter-spacing: 0.01em !important;
    text-transform: none !important;
    padding: 0 !important;
}
[data-testid="stExpander"] summary:hover { color: #4a6a88 !important; }
/* Number input */
[data-testid="stNumberInput"] input {
    font-family: 'Inter', system-ui, sans-serif !important;
    font-size: 0.82rem !important;
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 6px !important;
    color: #c8ddf0 !important;
}
[data-testid="stNumberInput"] input:focus {
    border-color: rgba(245,197,24,0.4) !important;
    box-shadow: 0 0 0 3px rgba(245,197,24,0.08) !important;
}
/* Success/warning/error */
[data-testid="stAlert"] {
    border-radius: 8px !important;
    border: none !important;
    font-size: 0.8rem !important;
}
iframe { border: none !important; }

/* ── Typography helpers ──────────────────────────────────────────────────── */
.t-overline {
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #607888;
}
.t-label {
    font-size: 0.72rem;
    font-weight: 500;
    color: #8aabb8;
}
.t-body { font-size: 0.82rem; color: #a8c4d8; }
.t-muted { font-size: 0.72rem; color: #607888; }

/* ── Layout spacers ──────────────────────────────────────────────────────── */
.gap-xs  { height: 0.5rem; }
.gap-sm  { height: 1rem; }
.gap-md  { height: 1.75rem; }
.gap-lg  { height: 2.5rem; }

/* ── Wordmark / nav ──────────────────────────────────────────────────────── */
.topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0 1rem;
    margin-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.wordmark {
    font-size: 1.45rem;
    font-weight: 900;
    color: #e8f2fc;
    letter-spacing: -0.04em;
    line-height: 1.25;
    display: block;
    overflow: visible;
}
.wordmark .q {
    color: #f5c518;
    text-shadow: 0 0 22px rgba(245,197,24,0.4), 0 0 6px rgba(245,197,24,0.25);
}
.topbar-meta {
    font-size: 0.72rem;
    color: #8aabb8;
    font-weight: 500;
    line-height: 1.5;
    text-align: right;
}

/* ── Page navigation links ───────────────────────────────────────────────── */
.page-nav-strip {
    display: flex;
    gap: 0.15rem;
    margin-bottom: 1.5rem;
    padding-bottom: 10px;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
[data-testid="stPageLink"] {
    display: inline-block !important;
}
[data-testid="stPageLink"] > a,
[data-testid="stPageLink"] > a:visited {
    font-size: 0.72rem !important;
    font-weight: 500 !important;
    color: #607888 !important;
    text-decoration: none !important;
    padding: 4px 10px !important;
    border-radius: 5px !important;
    border: 1px solid rgba(255,255,255,0.05) !important;
    background: rgba(255,255,255,0.02) !important;
    transition: color 0.12s, background 0.12s !important;
    white-space: nowrap !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 4px !important;
}
[data-testid="stPageLink"] > a:hover {
    color: #c8ddf0 !important;
    background: rgba(255,255,255,0.05) !important;
}
.page-nav-active-label {
    font-size: 0.72rem;
    font-weight: 600;
    color: #f5c518;
    padding: 4px 10px;
    border-radius: 5px;
    border: 1px solid rgba(245,197,24,0.2);
    background: rgba(245,197,24,0.06);
    white-space: nowrap;
}

/* ── Segment controls (coupon / budget) ──────────────────────────────────── */
.seg-group {
    display: inline-flex;
    gap: 0;
    background: rgba(255,255,255,0.03);
    border-radius: 7px;
    padding: 3px;
    margin-bottom: 1rem;
}
.seg-btn {
    padding: 5px 16px;
    border-radius: 5px;
    font-size: 0.78rem;
    font-weight: 500;
    color: #8aabb8;
    cursor: pointer;
    border: none;
    background: transparent;
    transition: all 0.1s;
    white-space: nowrap;
}
.seg-btn.active {
    background: #0f2035;
    color: #e8f2fc;
    font-weight: 600;
}

/* ── Strategy selector ───────────────────────────────────────────────────── */
.strat-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 1rem;
}
.strat-tile {
    padding: 10px 12px 8px;
    border-radius: 10px;
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.05);
    cursor: pointer;
    transition: background 0.12s, box-shadow 0.12s;
    position: relative;
    overflow: hidden;
    margin-bottom: 4px;
}
.strat-tile:hover { background: rgba(255,255,255,0.04); }
.strat-tile.active {
    background: linear-gradient(135deg, rgba(245,197,24,0.13) 0%, rgba(245,197,24,0.04) 100%);
    border-color: rgba(245,197,24,0.45);
    box-shadow: 0 0 18px rgba(245,197,24,0.07), inset 0 1px 0 rgba(245,197,24,0.12);
}
.strat-tile-badge {
    font-size: 0.58rem;
    font-weight: 700;
    color: #f5c518;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 5px;
    height: 12px;
}
.strat-tile-name { display: none; }
.strat-tile-desc { display: none; }
.strat-tile-stat {
    display: flex;
    flex-direction: column;
    gap: 3px;
}
.strat-stat-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}
.strat-stat-lbl { font-size: 0.63rem; color: #607888; font-weight: 500; }
.strat-stat-val { font-size: 0.78rem; font-weight: 700; color: #8aaec8; }
.strat-stat-val.gold   { color: #f5c518; }
.strat-stat-val.green  { color: #3aaa78; }
.strat-stat-val.muted  { color: #2e4a64; }

/* ── Hero metrics (top of page) ──────────────────────────────────────────── */
.hero-band {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 1fr;
    gap: 10px;
    margin-bottom: 1.5rem;
}
.hero-metric {
    padding: 16px 18px;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.25), inset 0 1px 0 rgba(255,255,255,0.04);
    backdrop-filter: blur(4px);
}
.hero-metric + .hero-metric { }
.hero-val {
    font-size: 1.65rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.hero-lbl {
    font-size: 0.68rem;
    font-weight: 500;
    color: #8aabb8;
    letter-spacing: 0.01em;
}
.hero-sub {
    font-size: 0.62rem;
    color: #607888;
    margin-top: 3px;
}

/* ── Payout bar ──────────────────────────────────────────────────────────── */
.pay-wrap { margin-bottom: 2.5rem; }
.pay-label-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}
.pay-track-outer {
    position: relative;
    height: 5px;
    background: rgba(255,255,255,0.06);
    border-radius: 3px;
    margin-bottom: 22px;
}
.pay-track-fill {
    position: absolute;
    top: 0;
    height: 5px;
    background: rgba(245,197,24,0.2);
    border-radius: 3px;
}
.pay-track-median {
    position: absolute;
    top: -2px;
    width: 4px;
    height: 9px;
    background: #f5c518;
    border-radius: 2px;
    box-shadow: 0 0 8px rgba(245,197,24,0.5);
}
.pay-tick {
    position: absolute;
    top: 11px;
    transform: translateX(-50%);
    text-align: center;
}
.pay-tick-val { font-size: 0.67rem; font-weight: 600; color: #a8c4d8; white-space: nowrap; }
.pay-tick-lbl { font-size: 0.6rem; color: #607888; margin-top: 1px; white-space: nowrap; }
.pay-tick-lbl.gold { color: #f5c518; }
.pay-footnote { font-size: 0.65rem; color: #607888; margin-top: 4px; }

/* ── Coupon list ─────────────────────────────────────────────────────────── */
.cpn-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.75rem;
}
.cpn-title { font-size: 0.78rem; font-weight: 600; color: #8aabb8; }
.cpn-meta-inline { font-size: 0.72rem; color: #607888; }

/* Meta sidebar */
.meta-stat {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 7px 0;
}
.meta-stat + .meta-stat {
    border-top: 1px solid rgba(255,255,255,0.04);
}
.meta-stat-lbl { font-size: 0.72rem; color: #607888; }
.meta-stat-val { font-size: 0.82rem; font-weight: 600; color: #c8ddf0; }
.meta-stat-val.pos { color: #3aaa78; }
.meta-stat-val.neg { color: #e07a5f; }

/* ── Omsetning CTA ───────────────────────────────────────────────────────── */
.om-cta {
    padding: 16px 20px;
    background: rgba(245,197,24,0.05);
    border-radius: 10px;
    text-align: center;
    margin-bottom: 2.5rem;
}
.om-cta-txt { font-size: 0.78rem; color: #8aaec8; margin-bottom: 4px; }
.om-cta-sub { font-size: 0.67rem; color: #2e4a64; }

/* ── Analysis cards (per-match) ──────────────────────────────────────────── */
.match-card {
    padding: 14px 0;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.match-card:last-child { border-bottom: none; }
.match-card-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.match-teams { font-size: 0.82rem; font-weight: 600; color: #c8ddf0; }
.match-pick {
    font-size: 1rem;
    font-weight: 800;
    color: #f5c518;
    min-width: 32px;
    text-align: right;
}
.match-card-bars { margin-bottom: 6px; }
.bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
}
.bar-lbl { font-size: 0.65rem; color: #607888; width: 12px; text-align: right; flex-shrink: 0; }
.bar-track {
    flex: 1;
    height: 4px;
    background: rgba(255,255,255,0.05);
    border-radius: 2px;
    overflow: hidden;
}
.bar-fill { height: 4px; border-radius: 2px; }
.bar-pct { font-size: 0.65rem; color: #607888; width: 28px; text-align: right; flex-shrink: 0; }
.match-card-bottom {
    display: flex;
    gap: 16px;
}
.match-chip {
    font-size: 0.67rem;
    color: #607888;
}
.match-chip strong { color: #8aabb8; font-weight: 600; }
.match-chip.highlight strong { color: #3aaa78; }
.match-chip.coverage { color: #8aabb8; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_matches(coupon_key: str) -> list[Match]:
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
        run_model(m, enrichment_map.get(i))
        classify_match(m)
        matches.append(m)
    return matches


def compute_pool_value_score(matches: list[Match], picks: dict) -> float | None:
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


def _fmt_kr(v: int) -> str:
    """Format NOK value compactly: 450000 → '450k', 1200000 → '1.2M'"""
    if v >= 1_000_000:
        m = v / 1_000_000
        return f"{m:.1f}M" if m < 10 else f"{m:.0f}M"
    return f"{v // 1000}k"


_CONVICTION_PP = 10.0  # edge threshold (pp) that marks a meaningful crowd mispricing


def render_coupon_list(matches: list[Match], picks: dict) -> None:
    """Coupon rows — conviction plays (large crowd edge) visually distinguished from necessary plays."""
    _dot = {1: "", 2: " &#9680;", 3: " &#9679;"}

    # Columns: [name] [pick] [edge — primary signal] [conf] [VI]
    _cols = "1fr 52px 68px 38px 48px"
    _gap  = "gap: 0 10px;"

    _th = "font-size:0.58rem;color:#2e4a64;font-weight:600;letter-spacing:0.07em;text-transform:uppercase;"
    header = (
        f"<div style='display:grid;grid-template-columns:{_cols};"
        f"align-items:center;padding:4px 0 7px;{_gap}"
        f"border-bottom:1px solid rgba(255,255,255,0.06);margin-bottom:3px;'>"
        f"<span style='{_th}'>Kamp</span>"
        f"<span style='{_th}'>Pick</span>"
        f"<span style='{_th}text-align:right;'>Edge</span>"
        f"<span style='{_th}text-align:right;'>Konf</span>"
        f"<span style='{_th}text-align:right;'>VI</span>"
        f"</div>"
    )

    rows = ""
    for m in matches:
        n      = len(picks[m.number])
        rec    = m.recommendation or ""
        pick_s = "/".join(picks[m.number]) + _dot[n]
        conf   = round(m.confidence * 100)

        val_f  = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        has_edge = val_f is not None and m.has_public_tips
        is_conviction = has_edge and abs(val_f) >= _CONVICTION_PP

        if has_edge:
            edge_s = f"{val_f:+.0f}pp"
        else:
            edge_s = "—"

        prob_r = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec, 0)
        pub_r  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi     = compute_value_index(prob_r, pub_r)
        vi_s   = f"{vi:.2f}×" if vi else "—"

        if is_conviction:
            # Conviction play: crowd meaningfully wrong — edge is the story
            name_col  = "#e8f2fc"
            edge_col  = "#f5c518" if (val_f or 0) > 0 else "#e07a5f"
            edge_size = "0.88rem"
            edge_wt   = "800"
            vi_col    = "#3aaa78" if (vi or 0) >= 1.1 else "#607888"
            row_bg    = "background:rgba(245,197,24,0.025);"
            left_bar  = (
                "border-left:2px solid rgba(245,197,24,0.35);"
                "padding-left:10px;margin-left:-2px;"
            )
        else:
            # Necessary play: model and crowd broadly agree — muted presentation
            name_col  = "#8aabb8"
            edge_col  = "#2e4a64"
            edge_size = "0.65rem"
            edge_wt   = "500"
            vi_col    = "#2e4a64"
            row_bg    = ""
            left_bar  = "padding-left:12px;"

        rows += (
            f"<div style='display:grid;grid-template-columns:{_cols};"
            f"align-items:center;padding:8px 0;{_gap}"
            f"border-bottom:1px solid rgba(255,255,255,0.03);{row_bg}'>"
            f"<span style='font-size:0.82rem;color:{name_col};font-weight:500;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;{left_bar}'>{m.label}</span>"
            f"<span style='font-size:0.88rem;font-weight:800;color:#f5c518;'>{pick_s}</span>"
            f"<span style='font-size:{edge_size};color:{edge_col};text-align:right;"
            f"font-weight:{edge_wt};font-variant-numeric:tabular-nums;'>{edge_s}</span>"
            f"<span style='font-size:0.65rem;color:#607888;text-align:right;"
            f"font-variant-numeric:tabular-nums;'>{conf}%</span>"
            f"<span style='font-size:0.65rem;color:{vi_col};text-align:right;"
            f"font-variant-numeric:tabular-nums;'>{vi_s}</span>"
            f"</div>"
        )

    html = (
        f"<div style='font-family:Inter,\"Segoe UI\",system-ui,sans-serif;'>"
        f"{header}{rows}"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_match_analysis(matches: list[Match], picks: dict) -> None:
    """Per-match analysis — edge leads, bars as supporting evidence."""
    H_COL, U_COL, B_COL = "#4a80b0", "#3a4a58", "#a07020"

    # Sort by edge magnitude descending — matches with biggest crowd mispricing first
    def _edge_mag(m):
        rec = m.recommendation or ""
        v = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        return abs(v) if (v is not None and m.has_public_tips) else 0.0

    sorted_matches = sorted(matches, key=_edge_mag, reverse=True)

    cards = ""
    for m in sorted_matches:
        n   = len(picks[m.number])
        rec = m.recommendation or ""
        cov = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}[n]
        cov_col = {1: "#2e4a64", 2: "#7a6020", 3: "#7a2020"}[n]
        conf = round(m.confidence * 100)

        val_f = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        has_edge = val_f is not None and m.has_public_tips
        is_conviction = has_edge and abs(val_f) >= _CONVICTION_PP

        if has_edge:
            edge_s = f"{val_f:+.0f}pp"
            edge_col = "#f5c518" if val_f > 0 else "#e07a5f"
        else:
            edge_s, edge_col = "—", "#2e4a64"

        prob_r = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec, 0)
        pub_r  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi     = compute_value_index(prob_r, pub_r)
        vi_col = "#3aaa78" if (vi or 0) >= 1.1 else "#2e4a64"

        def _bar(lbl, pct, color, is_rec):
            w = min(100, max(0, round(pct)))
            active_col = "#f5c518" if is_rec else color
            return (
                f"<div class='bar-row'>"
                f"<span class='bar-lbl'>{lbl}</span>"
                f"<div class='bar-track'><div class='bar-fill' style='width:{w}%;background:{active_col};'></div></div>"
                f"<span class='bar-pct'>{pct:.0f}%</span>"
                f"</div>"
            )

        bars = (
            _bar("H", m.prob_h * 100, H_COL, rec == "H") +
            _bar("U", m.prob_u * 100, U_COL, rec == "U") +
            _bar("B", m.prob_b * 100, B_COL, rec == "B")
        )

        chips = ""
        chips += f"<span class='match-chip' style='color:{cov_col};'>{cov}</span>"
        chips += f"<span class='match-chip'><strong>{conf}%</strong> konf.</span>"
        if vi:
            chips += f"<span class='match-chip'><strong style='color:{vi_col};'>VI {vi:.2f}×</strong></span>"

        # Header: edge is the lead number; pick + match name secondary
        _card_border = "border-left:2px solid rgba(245,197,24,0.3);" if is_conviction else "border-left:2px solid rgba(255,255,255,0.04);"
        cards += (
            f"<div class='match-card' style='{_card_border}padding-left:12px;'>"
            f"<div class='match-card-top'>"
            f"<div style='display:flex;flex-direction:column;gap:1px;'>"
            f"<span class='match-teams'>{m.label}</span>"
            f"<span style='font-size:0.6rem;color:#2e4a64;'>{m.number:02d}</span>"
            f"</div>"
            f"<div style='display:flex;flex-direction:column;align-items:flex-end;gap:2px;'>"
            f"<span class='match-pick'>{'/'.join(picks[m.number])}</span>"
            f"<span style='font-size:{'0.82rem' if is_conviction else '0.65rem'};"
            f"font-weight:{'700' if is_conviction else '400'};"
            f"color:{edge_col};font-variant-numeric:tabular-nums;'>{edge_s}</span>"
            f"</div>"
            f"</div>"
            f"<div class='match-card-bars'>{bars}</div>"
            f"<div class='match-card-bottom'>{chips}</div>"
            f"</div>"
        )

    st.markdown(
        f"<div style='font-family:Inter,\"Segoe UI\",system-ui,sans-serif;'>{cards}</div>",
        unsafe_allow_html=True,
    )


def render_conviction_summary(matches: list[Match], picks: dict) -> None:
    """Strip showing the top conviction plays before the coupon list."""
    plays = []
    for m in matches:
        rec = m.recommendation or ""
        val_f = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        if val_f is None or not m.has_public_tips:
            continue
        if abs(val_f) < _CONVICTION_PP:
            continue
        mod_pct = round({"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec, 0) * 100)
        pub_pct = round({"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec, 0) * 100)
        plays.append((abs(val_f), m, rec, val_f, mod_pct, pub_pct))

    plays.sort(key=lambda x: x[0], reverse=True)

    if not plays:
        st.markdown(
            '<div style="font-size:0.63rem;color:#1e3448;padding:7px 0 10px;'
            'border-top:1px solid rgba(255,255,255,0.04);">'
            'Ingen sterk folkeavvik denne runden.</div>',
            unsafe_allow_html=True,
        )
        return

    n_total  = len(plays)
    lbl      = "overbevisninger" if n_total != 1 else "overbevisning"
    rows_html = ""
    for _, m, rec, val_f, mod_pct, pub_pct in plays[:3]:
        direction = "undervurderer" if val_f > 0 else "overvurderer"
        edge_col  = "#f5c518" if val_f > 0 else "#e07a5f"
        n_marks   = len(picks.get(m.number, [rec]))
        cov_dot   = {1: "", 2: " ◐", 3: " ●"}.get(n_marks, "")
        pick_s    = "/".join(picks.get(m.number, [rec])) + cov_dot
        rows_html += (
            f'<div style="display:grid;grid-template-columns:1fr 44px 60px;'
            f'align-items:center;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.03);">'
            f'<div>'
            f'<div style="font-size:0.8rem;font-weight:600;color:#c8ddf0;">{m.label}</div>'
            f'<div style="font-size:0.62rem;color:#3a5a78;margin-top:2px;">'
            f'Modell {rec} {mod_pct}% · Folket {rec} {pub_pct}% '
            f'— folket {direction}</div>'
            f'</div>'
            f'<span style="font-size:0.88rem;font-weight:800;color:#f5c518;'
            f'text-align:center;">{pick_s}</span>'
            f'<span style="font-size:0.85rem;font-weight:800;color:{edge_col};'
            f'text-align:right;font-variant-numeric:tabular-nums;">{val_f:+.0f}pp</span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="font-family:Inter,\"Segoe UI\",system-ui,sans-serif;'
        f'margin-bottom:0.75rem;padding:8px 0;'
        f'border-top:1px solid rgba(255,255,255,0.05);">'
        f'<div style="display:flex;justify-content:space-between;align-items:baseline;'
        f'margin-bottom:5px;">'
        f'<span style="font-size:0.6rem;font-weight:600;color:#2e4a64;'
        f'text-transform:uppercase;letter-spacing:0.08em;">Folkeavvik</span>'
        f'<span style="font-size:0.6rem;color:#1e3448;">{n_total} {lbl}</span>'
        f'</div>'
        f'{rows_html}</div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════

# ── Topbar ────────────────────────────────────────────────────────────────────
coupon_key = st.session_state.coupon_key
budget     = st.session_state.budget
strategy   = st.session_state.strategy

st.markdown(f"""
<div class="topbar">
  <span class="wordmark">Tippe<span class="q">Q</span>ongen</span>
  <span class="topbar-meta">{_WEEK_LABEL} &nbsp;·&nbsp; {SHORT_LABELS.get(coupon_key, '')} &nbsp;·&nbsp; Frist {DEADLINES.get(coupon_key, '')}</span>
</div>
""", unsafe_allow_html=True)

# ── Page navigation ───────────────────────────────────────────────────────────
_na, _nb, _nc, _nd, _ne, _ = st.columns([1.4, 1, 1, 1, 1, 3.6])
with _na:
    st.markdown('<span class="page-nav-active-label">&#9679; Oversikt</span>', unsafe_allow_html=True)
with _nb:
    st.page_link("pages/5_Statistikk.py", label="Statistikk")
with _nc:
    st.page_link("pages/3_History.py", label="Historikk")
with _nd:
    st.page_link("pages/2_Results.py", label="Resultater")
with _ne:
    st.page_link("pages/4_Odds_Movement.py", label="Odds")
st.markdown('<div style="height:0.75rem;"></div>', unsafe_allow_html=True)

# ── Coupon + Budget selectors (compact row) ───────────────────────────────────
sel_col, _, bud_col = st.columns([3, 1, 5])

with sel_col:
    st.markdown('<div class="t-overline" style="margin-bottom:6px;">Kupong</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(len(COUPON_KEYS))
    for col, key in zip([c1, c2, c3], COUPON_KEYS):
        with col:
            active = coupon_key == key
            if st.button(SHORT_LABELS[key], key=f"tab_{key}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.coupon_key = key
                st.rerun()

with bud_col:
    st.markdown('<div class="t-overline" style="margin-bottom:6px;">Budsjett</div>', unsafe_allow_html=True)
    bb1, bb2, bb3, bb4 = st.columns(4)
    for col, amt in zip([bb1, bb2, bb3, bb4], BUDGET_OPTS):
        with col:
            active = budget == amt
            if st.button(f"{amt} kr", key=f"budget_{amt}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.budget = amt
                st.rerun()

st.markdown('<div class="gap-sm"></div>', unsafe_allow_html=True)

# ── Compute ───────────────────────────────────────────────────────────────────
coupon_key = st.session_state.coupon_key
budget     = st.session_state.budget
strategy   = st.session_state.strategy

matches  = load_matches(coupon_key)
picks, total_rows = optimize_coupon(matches, float(budget), strategy=strategy)
pvs      = compute_pool_value_score(matches, picks)
p_win    = compute_p_win(matches, picks)
pv_ratio = compute_pool_value_ratio(matches, picks)

_omsetning = st.session_state.omsetning
_sim = None
if _omsetning and _omsetning > 0:
    _sim = simulate_payout(matches, picks, total_rows, float(_omsetning))

# All-strategy comparison (for strategy tiles)
_cmp_data: list[tuple] = []
for _sk in _STRATEGY_KEYS:
    _sp, _sr = optimize_coupon(matches, float(budget), strategy=_sk)
    _cpw  = compute_p_win(matches, _sp)
    _cpvr = compute_pool_value_ratio(matches, _sp)
    _cmed: int | None = None
    if _omsetning and _omsetning > 0:
        _csim = simulate_payout(matches, _sp, _sr, float(_omsetning), n_sims=10_000)
        if _csim.get("n_winning_sims", 0) > 0:
            _cmed = _csim["median"]
    _cmp_data.append((_sk, _cpw, _cpvr, _cmed))

# Budget reducer comparison (current strategy × all budget levels vs anchor)
_anchor_picks, _anchor_rows = generate_anchor_coupon(matches, strategy)
_anchor_p_win = compute_p_win(matches, _anchor_picks)
_anchor_pvr   = compute_pool_value_ratio(matches, _anchor_picks)

_reducer_data: list[tuple] = []   # (_b, _br, _bp_win, _bp_pvr, _b_diff, coupon, nf, nh)
for _b in BUDGET_OPTS:
    if _b == budget:
        _bp, _br = picks, total_rows
    else:
        _bp, _br = optimize_coupon(matches, float(_b), strategy=strategy)
    _bp_win = compute_p_win(matches, _bp)
    _bp_pvr = compute_pool_value_ratio(matches, _bp)
    _b_diff = compare_coupons(_anchor_picks, _bp, matches)
    _b_nf   = sum(1 for m in matches if len(_bp.get(m.number, [])) == 3)
    _b_nh   = sum(1 for m in matches if len(_bp.get(m.number, [])) == 2)
    _reducer_data.append((_b, _br, _bp_win, _bp_pvr, _b_diff, _b_nf, _b_nh))

# ── Strategy selector ─────────────────────────────────────────────────────────
st.markdown('<div class="t-overline" style="margin-bottom:14px;">Strategi</div>', unsafe_allow_html=True)

sc1, sc2, sc3 = st.columns(3)
for col, (_sk, _cpw, _cpvr, _cmed) in zip([sc1, sc2, sc3], _cmp_data):
    with col:
        _active = strategy == _sk
        _tile_cls = "strat-tile active" if _active else "strat-tile"
        _badge = "★ Anbefalt" if _sk == "balanced" else "&nbsp;"
        _pw_s  = f"{_cpw*100:.1f}%"
        _pvr_s = f"{_cpvr:.2f}×" if _cpvr else "—"
        _med_s = _fmt_kr(_cmed) if _cmed else "—"
        _pvr_cls = "green" if (_cpvr or 0) >= 1.0 else "muted"
        _pw_cls  = "gold" if _active else ""
        st.markdown(f"""
<div class="{_tile_cls}">
  <div class="strat-tile-badge">{_badge}</div>
  <div class="strat-tile-name">{_STRATEGY_LABELS[_sk]}</div>
  <div class="strat-tile-desc">{_STRATEGY_DESC[_sk]}</div>
  <div class="strat-tile-stat">
    <div class="strat-stat-row">
      <span class="strat-stat-lbl">P(12/12)</span>
      <span class="strat-stat-val {_pw_cls}">{_pw_s}</span>
    </div>
    <div class="strat-stat-row">
      <span class="strat-stat-lbl">PVR</span>
      <span class="strat-stat-val {_pvr_cls}">{_pvr_s}</span>
    </div>
    <div class="strat-stat-row">
      <span class="strat-stat-lbl">Median</span>
      <span class="strat-stat-val">{_med_s}</span>
    </div>
  </div>
</div>""", unsafe_allow_html=True)
        if st.button(_STRATEGY_LABELS[_sk], key=f"strat_{_sk}",
                     use_container_width=True,
                     type="primary" if _active else "secondary"):
            st.session_state.strategy = _sk
            st.rerun()

st.markdown('<div class="gap-xs"></div>', unsafe_allow_html=True)

# ── Hero metrics ──────────────────────────────────────────────────────────────
_pwin_col = "#3aaa78" if p_win >= 0.05 else "#c8960e" if p_win >= 0.02 else "#e07a5f"
_pvr_col  = "#3aaa78" if (pv_ratio or 0) >= 1.0 else "#e07a5f"
_med_val  = _fmt_kr(_sim["median"]) if _sim and _sim.get("n_winning_sims", 0) > 0 else "—"
_p90_val  = _fmt_kr(_sim["p90"])    if _sim and _sim.get("n_winning_sims", 0) > 0 else "—"
_pvr_disp = f"{pv_ratio:.2f}×"      if pv_ratio else "—"
_pvr_sub  = "pool-edge" if (pv_ratio or 0) >= 1.0 else "under snittet"

st.markdown(f"""
<div class="hero-band">
  <div class="hero-metric">
    <div class="hero-val" style="color:{_pwin_col};">{p_win*100:.2f}%</div>
    <div class="hero-lbl">P(12/12)</div>
    <div class="hero-sub">Sjanse for 12 rette</div>
  </div>
  <div class="hero-metric">
    <div class="hero-val" style="color:#f5c518;">{_med_val}</div>
    <div class="hero-lbl">Median gevinst</div>
    <div class="hero-sub">ved 12 rette</div>
  </div>
  <div class="hero-metric">
    <div class="hero-val" style="color:{_pvr_col};">{_pvr_disp}</div>
    <div class="hero-lbl">Poolverdi ratio</div>
    <div class="hero-sub">{_pvr_sub}</div>
  </div>
  <div class="hero-metric">
    <div class="hero-val" style="color:#8aaec8;">{_p90_val}</div>
    <div class="hero-lbl">P90 gevinst</div>
    <div class="hero-sub">optimistisk scenario</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Omsetning callback ────────────────────────────────────────────────────────
def _on_om_change():
    v = st.session_state._om_raw
    st.session_state.omsetning = int(v) if v and v > 0 else None

st.markdown('<div class="gap-xs"></div>', unsafe_allow_html=True)

# ── Coupon + meta ─────────────────────────────────────────────────────────────
main_col, side_col = st.columns([7, 3])

with main_col:
    total_cost = total_rows  # 1 NOK per combination (cost_per_row=1.0 in optimizer)
    n_full = sum(1 for m in matches if len(picks[m.number]) == 3)
    n_half = sum(1 for m in matches if len(picks[m.number]) == 2)

    _cpn_label = SHORT_LABELS.get(coupon_key, "")
    render_conviction_summary(matches, picks)
    st.markdown(f"""
<div class="cpn-header">
  <span class="cpn-title">{_STRATEGY_LABELS[strategy]} &nbsp;&middot;&nbsp; {_cpn_label} &nbsp;&middot;&nbsp; {total_rows} rekker</span>
  <span class="cpn-meta-inline">{n_half} halvdekk &nbsp;&middot;&nbsp; {n_full} heldekkende</span>
</div>
""", unsafe_allow_html=True)
    render_coupon_list(matches, picks)

with side_col:
    remaining = float(budget) - total_cost
    rem_cls   = "pos" if remaining >= 0 else "neg"
    _pvr_sc   = "pos" if (pv_ratio or 0) >= 1.0 else "neg"
    _pvr_s2   = f"{pv_ratio:.2f}×" if pv_ratio else "—"
    _pvs_s    = f"{pvs:+.1f}pp" if pvs is not None else "—"
    _n_val    = sum(
        1 for m in matches if m.has_public_tips and m.recommendation and
        ({"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(m.recommendation) or 0) > 0
    )

    st.markdown(f"""
<div style="padding-top:1rem;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px 16px;">
  <div class="meta-stat">
    <span class="meta-stat-lbl">Rekker</span>
    <span class="meta-stat-val">{total_rows}</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Kostnad</span>
    <span class="meta-stat-val">{total_cost} NOK</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Rest av budsjett</span>
    <span class="meta-stat-val {rem_cls}">{remaining:+.0f} NOK</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">PVR</span>
    <span class="meta-stat-val {_pvr_sc}">{_pvr_s2}</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Poolverdi</span>
    <span class="meta-stat-val">{_pvs_s}</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Verdivalg</span>
    <span class="meta-stat-val">{_n_val} av 12</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Payout bar (compact, in sidebar) ──────────────────────────────────────
    if _sim and _sim.get("n_winning_sims", 0) > 0:
        _vmin = _sim["min"]
        _vmax = _sim.get("p99", _sim["max"])
        if _vmax <= _vmin:
            _vmax = _vmin + 1
        def _bp(v):
            return max(0.5, min(98.5, (v - _vmin) / (_vmax - _vmin) * 100))
        _rl = _bp(_sim["p10"])
        _rw = _bp(_sim["p90"]) - _rl
        _mp = _bp(_sim["median"]) - 0.2
        _ew = _sim.get("e_winners", 0)
        _p10_s = _fmt_kr(_sim["p10"])
        _med_s = _fmt_kr(_sim["median"])
        _p90_s = _fmt_kr(_sim["p90"])
        st.markdown(f"""
<div style="margin-top:12px;background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.06);border-radius:12px;padding:14px 16px;">
<div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;">
<span style="font-size:0.67rem;font-weight:500;color:#4a6a88;">Utdeling ved 12/12</span>
<span style="font-size:0.6rem;color:#2e4a64;">~{_ew:,} vinnere</span>
</div>
<div class="pay-track-outer" style="margin-bottom:14px;">
<div class="pay-track-fill" style="left:{_rl:.1f}%;width:{_rw:.1f}%;"></div>
<div class="pay-track-median" style="left:{_mp:.1f}%;"></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:2px;">
<div style="text-align:left;">
<div style="font-size:0.65rem;font-weight:600;color:#8aaec8;">{_p10_s}</div>
<div style="font-size:0.57rem;color:#2e4a64;">P10</div>
</div>
<div style="text-align:center;">
<div style="font-size:0.65rem;font-weight:700;color:#f5c518;">{_med_s}</div>
<div style="font-size:0.57rem;color:#f5c518;">Median</div>
</div>
<div style="text-align:right;">
<div style="font-size:0.65rem;font-weight:600;color:#8aaec8;">{_p90_s}</div>
<div style="font-size:0.57rem;color:#2e4a64;">P90</div>
</div>
</div>
</div>
""", unsafe_allow_html=True)

    # ── Omsetning input ────────────────────────────────────────────────────────
    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
    st.number_input(
        "Omsetning (NOK)",
        key="_om_raw",
        min_value=0,
        max_value=200_000_000,
        value=int(_omsetning or 0),
        step=500_000,
        on_change=_on_om_change,
        label_visibility="visible",
        help="Finn aktuell omsetning på norsk-tipping.no",
    )

    st.markdown('<div class="gap-xs"></div>', unsafe_allow_html=True)

    if st.button("Lagre kupong", use_container_width=True, type="secondary"):
        from db.schema import init_db as _init_db2
        from db.coupon import get_coupon_matches, get_best_odds
        from db.history import save_prediction, save_coupon_snapshot

        _init_db2()
        coupon_id = f"{coupon_key}-{_iso.week:02d}-{_iso.year}"
        db_matches = get_coupon_matches(coupon_id)
        fid_map = {r["match_number"]: r["fixture_id"] for r in db_matches}

        saved, missing = 0, 0
        for m in matches:
            fid = fid_map.get(m.number)
            if not fid:
                missing += 1
                continue
            best = get_best_odds(fid)
            save_prediction(
                coupon_id=coupon_id, fixture_id=fid,
                match_number=m.number,
                recommended_pick=m.recommendation,
                picks=picks[m.number], confidence=m.confidence,
                implied_prob_h=m.prob_h, implied_prob_u=m.prob_u,
                implied_prob_b=m.prob_b,
                odds_h=best["odds_h"] if best else None,
                odds_u=best["odds_u"] if best else None,
                odds_b=best["odds_b"] if best else None,
                odds_source=best["source"] if best else None,
                pub_prob_h=m.pub_prob_h,
                pub_prob_u=m.pub_prob_u,
                pub_prob_b=m.pub_prob_b,
                value_h=m.value_h,
                value_u=m.value_u,
                value_b=m.value_b,
                crowd_disagreement_score=m.crowd_disagreement_score,
            )
            saved += 1

        if saved > 0:
            save_coupon_snapshot(
                coupon_id=coupon_id,
                strategy=strategy,
                budget_nok=float(budget),
                total_rows=total_rows,
                p_win=p_win,
                pvr=pv_ratio,
            )

        if saved == len(matches):
            st.success(f"Lagret {saved} kamper.")
        elif saved > 0:
            st.warning(f"{saved}/{len(matches)} lagret — {missing} mangler fixture_id.")
        else:
            st.error("Ingen lagret — kjør sync.py --seed-only.")

st.markdown('<div class="gap-sm"></div>', unsafe_allow_html=True)

# ── Progressive disclosure ────────────────────────────────────────────────────
with st.expander("Kampanalyse — sannsynligheter og pool-verdi per kamp"):
    render_match_analysis(matches, picks)

with st.expander("Strategisammenligning"):
    _has_med = any(d[3] is not None for d in _cmp_data)
    _rows_html = ""
    for _sk, _cpw, _cpvr, _cmed in _cmp_data:
        _act = _sk == strategy
        _row_style = "background:rgba(255,255,255,0.03);" if _act else ""
        _name = ("▶ " if _act else " ") + _STRATEGY_LABELS[_sk]
        _pw_s  = f"{_cpw*100:.2f}%"
        _pvr_s = f"{_cpvr:.2f}×" if _cpvr else "—"
        _pvr_col2 = "#3aaa78" if (_cpvr or 0) >= 1.0 else "#4a6a88"
        _rows_html += (
            f"<tr style='{_row_style}'>"
            f"<td style='padding:8px 12px;font-size:0.8rem;"
            f"color:{'#c8ddf0' if _act else '#4a6a88'};font-weight:{'600' if _act else '400'};'>{_name}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#8aaec8;'>{_pw_s}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:{_pvr_col2};font-weight:600;'>{_pvr_s}</td>"
        )
        if _has_med:
            _med_s2 = _fmt_kr(_cmed) if _cmed else "—"
            _rows_html += f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#4a6a88;'>{_med_s2}</td>"
        _rows_html += "</tr>"

    _med_th2 = "<th style='text-align:right;'>Median</th>" if _has_med else ""
    _th_s = "padding:6px 12px;font-size:0.67rem;color:#2e4a64;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid rgba(255,255,255,0.06);"
    _med_th_html = f'<th style="{_th_s}text-align:right;">Median</th>' if _has_med else ""
    _med_note    = "<div style='font-size:0.65rem;color:#2e4a64;margin-top:8px;'>* 10 000 simuleringer per strategi</div>" if _has_med else ""
    st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-family:Inter,'Segoe UI',system-ui,sans-serif;">
<thead>
<tr>
<th style="{_th_s}text-align:left;">Strategi</th>
<th style="{_th_s}text-align:right;">P(12/12)</th>
<th style="{_th_s}text-align:right;">PVR</th>
{_med_th_html}
</tr>
</thead>
<tbody>{_rows_html}</tbody>
</table>
{_med_note}
""", unsafe_allow_html=True)

with st.expander("Budsjettsammenligning — optimal vs budsjett"):
    def _fmt_cov_diff(diff: dict) -> str:
        parts = []
        if diff["full_to_single"] > 0:
            parts.append(f"−{diff['full_to_single']} heldekk→singel")
        if diff["full_to_half"] > 0:
            parts.append(f"−{diff['full_to_half']} heldekk→halvdekk")
        if diff["half_to_single"] > 0:
            parts.append(f"−{diff['half_to_single']} halvdekk→singel")
        if diff["single_to_full"] > 0:
            parts.append(f"+{diff['single_to_full']} singel→heldekk")
        if diff["half_to_full"] > 0:
            parts.append(f"+{diff['half_to_full']} halvdekk→heldekk")
        if diff["single_to_half"] > 0:
            parts.append(f"+{diff['single_to_half']} singel→halvdekk")
        return ", ".join(parts) if parts else "= Optimalt"

    _th_r = "padding:6px 12px;font-size:0.67rem;color:#2e4a64;font-weight:600;text-transform:uppercase;letter-spacing:0.05em;border-bottom:1px solid rgba(255,255,255,0.06);"
    _anch_pvr_s  = f"{_anchor_pvr:.2f}×" if _anchor_pvr else "—"
    _anch_nf = sum(1 for m in matches if len(_anchor_picks.get(m.number, [])) == 3)
    _anch_nh = sum(1 for m in matches if len(_anchor_picks.get(m.number, [])) == 2)

    _red_html = (
        "<tr style='background:rgba(245,197,24,0.08);'>"
        f"<td style='padding:8px 12px;font-size:0.8rem;color:#f5c518;font-weight:700;'>★ Optimalt</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#8aaec8;'>{_anchor_rows}</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#8aaec8;'>{_anch_nf}H·{_anch_nh}½</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#c8ddf0;font-weight:600;'>{_anchor_p_win*100:.2f}%</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#3aaa78;font-weight:600;'>{_anch_pvr_s}</td>"
        f"<td style='padding:8px 12px;font-size:0.8rem;color:#4a6a88;'>—</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#4a6a88;'>—</td>"
        f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#4a6a88;'>—</td>"
        "</tr>"
    )

    for _b, _br, _bp_win, _bp_pvr, _b_diff, _b_nf, _b_nh in _reducer_data:
        _is_sel   = _b == budget
        _row_bg   = "background:rgba(255,255,255,0.03);" if _is_sel else ""
        _lbl      = ("▶ " if _is_sel else "") + f"{_b} NOK"
        _lbl_col  = "#c8ddf0" if _is_sel else "#4a6a88"
        _lbl_wt   = "700" if _is_sel else "400"

        _pvr_s    = f"{_bp_pvr:.2f}×" if _bp_pvr else "—"
        _pvr_col  = "#3aaa78" if (_bp_pvr or 0) >= 1.0 else "#4a6a88"
        _cov_txt  = _fmt_cov_diff(_b_diff)
        _cov_col  = ("#4a6a88" if _cov_txt == "= Optimalt"
                     else "#3aaa78" if _cov_txt.startswith("+")
                     else "#e07a5f")

        _p_delta   = _bp_win - _anchor_p_win
        _pvr_delta = (_bp_pvr - _anchor_pvr) if (_bp_pvr is not None and _anchor_pvr is not None) else None

        _p_d_s   = ("+" if _p_delta >= 0 else "−") + f"{abs(_p_delta*100):.2f} pp"
        _p_d_col = "#3aaa78" if _p_delta >= 0 else "#e07a5f"
        if _pvr_delta is None:
            _pvr_d_s, _pvr_d_col = "—", "#4a6a88"
        else:
            _pvr_d_s   = ("+" if _pvr_delta >= 0 else "−") + f"{abs(_pvr_delta):.2f}×"
            _pvr_d_col = "#3aaa78" if _pvr_delta >= 0 else "#e07a5f"

        _red_html += (
            f"<tr style='{_row_bg}'>"
            f"<td style='padding:8px 12px;font-size:0.8rem;color:{_lbl_col};font-weight:{_lbl_wt};'>{_lbl}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#8aaec8;'>{_br}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#8aaec8;'>{_b_nf}H·{_b_nh}½</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:#c8ddf0;'>{_bp_win*100:.2f}%</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:{_pvr_col};font-weight:600;'>{_pvr_s}</td>"
            f"<td style='padding:8px 12px;font-size:0.8rem;color:{_cov_col};'>{_cov_txt}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:{_p_d_col};'>{_p_d_s}</td>"
            f"<td style='padding:8px 12px;text-align:right;font-size:0.8rem;color:{_pvr_d_col};'>{_pvr_d_s}</td>"
            "</tr>"
        )

    st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-family:Inter,'Segoe UI',system-ui,sans-serif;">
<thead><tr>
<th style="{_th_r}text-align:left;">Budsjett</th>
<th style="{_th_r}text-align:right;">Rekker</th>
<th style="{_th_r}text-align:right;">Dekning</th>
<th style="{_th_r}text-align:right;">P(12/12)</th>
<th style="{_th_r}text-align:right;">PVR</th>
<th style="{_th_r}text-align:left;">Endring vs optimalt</th>
<th style="{_th_r}text-align:right;">P‑tap</th>
<th style="{_th_r}text-align:right;">PVR‑tap</th>
</tr></thead>
<tbody>{_red_html}</tbody>
</table>
<div style="font-size:0.65rem;color:#2e4a64;margin-top:8px;">
★ Optimalt = beste form uten budsjetttak ({_anchor_rows} rekker, {_STRATEGY_LABELS[strategy]}-strategi, maks 1536 rekker).
&nbsp;&nbsp;H = heldekk &nbsp;·&nbsp; ½ = halvdekk
</div>
""", unsafe_allow_html=True)
