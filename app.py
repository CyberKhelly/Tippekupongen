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

_STRATEGY_KEYS = ["safe", "balanced", "value", "jackpot"]
_STRATEGY_LABELS = {
    "safe":     "Safe",
    "balanced": "Balansert",
    "value":    "Verdi",
    "jackpot":  "Jackpot",
}
_STRATEGY_DESC = {
    "safe":     "Maks P(12/12). Minst risiko.",
    "balanced": "Balanse sjanse og verdi.",
    "value":    "Pool-edge via CDS-justering.",
    "jackpot":  "Maks PVR. Høy potensiell gevinst.",
}
_STRATEGY_NARRATIVES = {
    "safe":     "Safe ignorerer folkemening — maksimerer 12/12-sjansen.",
    "balanced": "Balansert bruker mild crowd-justering — god balanse mellom sjanse og poolunikhet.",
    "value":    "Verdi lar crowd-avvik (CDS) styre halvdekk — noe lavere 12/12-sjanse, høyere forventet utdeling.",
    "jackpot":  "Jackpot maksimerer PVR — lavest 12/12-sjanse, men høyest forventet utdeling ved gevinst.",
}

# ── Session state ──────────────────────────────────────────────────────────────
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

# ── CSS ────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

/* ── Reset & shell ───────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
.stApp {
    background: #08111c;
    font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
}
[data-testid="stHeader"] {
    background: #08111c !important;
    border-bottom: none !important;
}
.block-container {
    max-width: 1160px !important;
    margin: 0 auto !important;
    padding-top: 3rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
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
    color: #4a6a88 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}
[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: rgba(255,255,255,0.04) !important;
    color: #8aaec8 !important;
    border-color: rgba(255,255,255,0.14) !important;
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
    color: #2e4a64;
}
.t-label {
    font-size: 0.72rem;
    font-weight: 500;
    color: #4a6a88;
}
.t-body { font-size: 0.82rem; color: #8aaec8; }
.t-muted { font-size: 0.72rem; color: #2e4a64; }

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
    margin-bottom: 3rem;
}
.wordmark {
    font-size: 1.05rem;
    font-weight: 800;
    color: #e0eaf4;
    letter-spacing: -0.02em;
}
.wordmark .q { color: #f5c518; }
.topbar-meta {
    font-size: 0.72rem;
    color: #2e4a64;
    font-weight: 500;
}

/* ── Segment controls (coupon / budget) ──────────────────────────────────── */
.seg-group {
    display: inline-flex;
    gap: 0;
    background: rgba(255,255,255,0.03);
    border-radius: 7px;
    padding: 3px;
    margin-bottom: 2.5rem;
}
.seg-btn {
    padding: 5px 16px;
    border-radius: 5px;
    font-size: 0.78rem;
    font-weight: 500;
    color: #4a6a88;
    cursor: pointer;
    border: none;
    background: transparent;
    transition: all 0.1s;
    white-space: nowrap;
}
.seg-btn.active {
    background: #0f2035;
    color: #e0eaf4;
    font-weight: 600;
}

/* ── Strategy selector ───────────────────────────────────────────────────── */
.strat-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 10px;
    margin-bottom: 2.5rem;
}
.strat-tile {
    padding: 16px 18px 14px;
    border-radius: 10px;
    background: rgba(255,255,255,0.025);
    cursor: pointer;
    transition: background 0.12s, box-shadow 0.12s;
    position: relative;
    overflow: hidden;
}
.strat-tile:hover { background: rgba(255,255,255,0.045); }
.strat-tile.active {
    background: rgba(245,197,24,0.07);
    box-shadow: inset 0 0 0 1.5px rgba(245,197,24,0.35);
}
.strat-tile-badge {
    font-size: 0.6rem;
    font-weight: 700;
    color: #f5c518;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 8px;
    height: 14px;
}
.strat-tile-name {
    font-size: 0.88rem;
    font-weight: 700;
    color: #c8ddf0;
    margin-bottom: 4px;
    letter-spacing: -0.01em;
}
.strat-tile-desc {
    font-size: 0.7rem;
    color: #2e4a64;
    line-height: 1.4;
    margin-bottom: 14px;
}
.strat-tile-stat {
    display: flex;
    flex-direction: column;
    gap: 5px;
}
.strat-stat-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
}
.strat-stat-lbl { font-size: 0.67rem; color: #2e4a64; font-weight: 500; }
.strat-stat-val { font-size: 0.82rem; font-weight: 700; color: #8aaec8; }
.strat-stat-val.gold   { color: #f5c518; }
.strat-stat-val.green  { color: #3aaa78; }
.strat-stat-val.muted  { color: #2e4a64; }

/* ── Hero metrics (top of page) ──────────────────────────────────────────── */
.hero-band {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr 1fr;
    gap: 0;
    margin-bottom: 2.5rem;
}
.hero-metric {
    padding: 0 24px 0 0;
}
.hero-metric + .hero-metric {
    padding-left: 24px;
    border-left: 1px solid rgba(255,255,255,0.06);
}
.hero-val {
    font-size: 2rem;
    font-weight: 800;
    letter-spacing: -0.04em;
    line-height: 1;
    margin-bottom: 6px;
    font-variant-numeric: tabular-nums;
}
.hero-lbl {
    font-size: 0.72rem;
    font-weight: 500;
    color: #4a6a88;
    letter-spacing: 0.01em;
}
.hero-sub {
    font-size: 0.67rem;
    color: #2e4a64;
    margin-top: 2px;
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
.pay-tick-val { font-size: 0.67rem; font-weight: 600; color: #8aaec8; white-space: nowrap; }
.pay-tick-lbl { font-size: 0.6rem; color: #2e4a64; margin-top: 1px; white-space: nowrap; }
.pay-tick-lbl.gold { color: #f5c518; }
.pay-footnote { font-size: 0.65rem; color: #1e3a54; margin-top: 4px; }

/* ── Coupon list ─────────────────────────────────────────────────────────── */
.cpn-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 1rem;
}
.cpn-title { font-size: 0.78rem; font-weight: 600; color: #4a6a88; }
.cpn-meta-inline { font-size: 0.72rem; color: #2e4a64; }

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
.meta-stat-lbl { font-size: 0.72rem; color: #2e4a64; }
.meta-stat-val { font-size: 0.82rem; font-weight: 600; color: #8aaec8; }
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
.bar-lbl { font-size: 0.65rem; color: #2e4a64; width: 12px; text-align: right; flex-shrink: 0; }
.bar-track {
    flex: 1;
    height: 4px;
    background: rgba(255,255,255,0.05);
    border-radius: 2px;
    overflow: hidden;
}
.bar-fill { height: 4px; border-radius: 2px; }
.bar-pct { font-size: 0.65rem; color: #2e4a64; width: 28px; text-align: right; flex-shrink: 0; }
.match-card-bottom {
    display: flex;
    gap: 16px;
}
.match-chip {
    font-size: 0.67rem;
    color: #2e4a64;
}
.match-chip strong { color: #4a6a88; font-weight: 600; }
.match-chip.highlight strong { color: #3aaa78; }
.match-chip.coverage { color: #4a6a88; }
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


def render_coupon_list(matches: list[Match], picks: dict) -> None:
    """Coupon as a clean pick list — no table borders, typography-led."""
    _cov_dot = {1: "", 2: "&#9680;", 3: "&#9679;"}
    _cov_col = {1: "#2e4a64", 2: "#8a6a00", 3: "#7a3030"}

    rows = ""
    for m in matches:
        n      = len(picks[m.number])
        rec    = m.recommendation or ""
        pick_s = "/".join(picks[m.number])

        conf   = round(m.confidence * 100)
        dot    = _cov_dot[n]
        dot_col = _cov_col[n]

        val_f  = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        if val_f is not None and m.has_public_tips:
            val_s  = f"{val_f:+.1f}pp"
            val_col = "#3aaa78" if val_f > 0 else "#e07a5f"
        else:
            val_s, val_col = "", "#2e4a64"

        prob_r = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(rec, 0)
        pub_r  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(rec)
        vi     = compute_value_index(prob_r, pub_r)
        vi_s   = f"VI {vi:.2f}×" if vi else ""
        vi_col = "#3aaa78" if (vi or 0) >= 1.1 else "#2e4a64"

        val_html = (f"<span style='font-size:0.67rem;color:{val_col};font-weight:600;"
                    f"margin-left:10px;'>{val_s}</span>") if val_s else ""
        vi_html  = (f"<span style='font-size:0.67rem;color:{vi_col};"
                    f"margin-left:8px;'>{vi_s}</span>") if vi_s else ""
        dot_html = (f"<span style='font-size:0.7rem;color:{dot_col};"
                    f"margin-left:4px;'>{dot}</span>") if dot else ""

        rows += (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:9px 0;border-bottom:1px solid rgba(255,255,255,0.035);'>"
            f"<div>"
            f"<span style='font-size:0.65rem;color:#2e4a64;margin-right:10px;"
            f"font-variant-numeric:tabular-nums;'>{m.number:02d}</span>"
            f"<span style='font-size:0.82rem;color:#c8ddf0;font-weight:500;'>{m.label}</span>"
            f"</div>"
            f"<div style='display:flex;align-items:center;'>"
            f"{val_html}{vi_html}"
            f"<span style='font-size:0.67rem;color:#4a6a88;margin-left:12px;'>{conf}%</span>"
            f"<span style='font-size:0.95rem;font-weight:800;color:#f5c518;"
            f"min-width:36px;text-align:right;margin-left:12px;'>{pick_s}</span>"
            f"{dot_html}"
            f"</div>"
            f"</div>"
        )

    html = (
        f"<div style='font-family:Inter,\"Segoe UI\",system-ui,sans-serif;'>"
        f"{rows}"
        f"</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def render_match_analysis(matches: list[Match], picks: dict) -> None:
    """Per-match analysis with probability bars — used inside expander."""
    H_COL, U_COL, B_COL = "#4a80b0", "#3a4a58", "#a07020"

    cards = ""
    for m in matches:
        n   = len(picks[m.number])
        rec = m.recommendation or ""
        cov = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}[n]
        cov_col = {1: "#2e4a64", 2: "#7a6020", 3: "#7a2020"}[n]
        conf = round(m.confidence * 100)

        val_f = {"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(rec)
        val_s = (f"{val_f:+.1f}pp" if val_f is not None and m.has_public_tips
                 else "")
        val_col = "#3aaa78" if (val_f or 0) > 0 else "#e07a5f" if val_f else "#2e4a64"

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
        chips += f"<span class='match-chip'><strong>{conf}%</strong> konf.</span>"
        chips += f"<span class='match-chip' style='color:{cov_col};'>{cov}</span>"
        if val_s:
            chips += f"<span class='match-chip'><strong style='color:{val_col};'>{val_s}</strong></span>"
        if vi:
            chips += f"<span class='match-chip'><strong style='color:{vi_col};'>VI {vi:.2f}×</strong></span>"

        cards += (
            f"<div class='match-card'>"
            f"<div class='match-card-top'>"
            f"<div>"
            f"<span style='font-size:0.65rem;color:#2e4a64;margin-right:8px;'>{m.number:02d}</span>"
            f"<span class='match-teams'>{m.label}</span>"
            f"</div>"
            f"<span class='match-pick'>{'/'.join(picks[m.number])}</span>"
            f"</div>"
            f"<div class='match-card-bars'>{bars}</div>"
            f"<div class='match-card-bottom'>{chips}</div>"
            f"</div>"
        )

    st.markdown(
        f"<div style='font-family:Inter,\"Segoe UI\",system-ui,sans-serif;'>{cards}</div>",
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
  <span class="wordmark">Tippe<span class="q">Q</span>pongen</span>
  <span class="topbar-meta">{_WEEK_LABEL} &nbsp;·&nbsp; {SHORT_LABELS.get(coupon_key, '')} &nbsp;·&nbsp; Frist {DEADLINES.get(coupon_key, '')}</span>
</div>
""", unsafe_allow_html=True)

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

st.markdown('<div class="gap-lg"></div>', unsafe_allow_html=True)

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

# ── Strategy selector ─────────────────────────────────────────────────────────
st.markdown('<div class="t-overline" style="margin-bottom:14px;">Strategi</div>', unsafe_allow_html=True)

sc1, sc2, sc3, sc4 = st.columns(4)
for col, (_sk, _cpw, _cpvr, _cmed) in zip([sc1, sc2, sc3, sc4], _cmp_data):
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

st.markdown('<div class="gap-lg"></div>', unsafe_allow_html=True)

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

# ── Payout bar ────────────────────────────────────────────────────────────────
def _on_om_change():
    v = st.session_state._om_raw
    st.session_state.omsetning = int(v) if v and v > 0 else None

if _sim and _sim.get("n_winning_sims", 0) > 0:
    _vmin = _sim["min"]
    _vmax = _sim.get("p99", _sim["max"])
    if _vmax <= _vmin:
        _vmax = _vmin + 1

    def _bp(v):
        return max(0.5, min(98.5, (v - _vmin) / (_vmax - _vmin) * 100))

    _ticks = [
        (_bp(_sim["min"]),    _fmt_kr(_sim["min"]),    "Min",    False),
        (_bp(_sim["p10"]),    _fmt_kr(_sim["p10"]),    "P10",    False),
        (_bp(_sim["median"]), _fmt_kr(_sim["median"]), "Median", True),
        (_bp(_sim["p90"]),    _fmt_kr(_sim["p90"]),    "P90",    False),
        (_bp(_vmax),          _fmt_kr(_vmax),           "P99",    False),
    ]
    _tick_html = "".join(
        f'<div class="pay-tick" style="left:{p:.1f}%;">'
        f'<div class="pay-tick-val">{v}</div>'
        f'<div class="pay-tick-lbl{"" if not g else " gold"}">{l}</div>'
        f'</div>'
        for p, v, l, g in _ticks
    )
    _rl = _bp(_sim["p10"])
    _rw = _bp(_sim["p90"]) - _rl
    _mp = _bp(_sim["median"]) - 0.2

    _ew = _sim.get("e_winners", 0)
    st.markdown(f"""
<div class="pay-wrap">
  <div class="pay-label-row">
    <span class="t-label">Utdelingsfordeling ved 12/12</span>
    <span class="t-muted">~{_ew:,} forventede vinnere</span>
  </div>
  <div class="pay-track-outer">
    <div class="pay-track-fill" style="left:{_rl:.1f}%;width:{_rw:.1f}%;"></div>
    <div class="pay-track-median" style="left:{_mp:.1f}%;"></div>
    {_tick_html}
  </div>
  <div class="pay-footnote">Simuleringsestimat &middot; 50 000 simuleringer &middot; 52% premieandel &middot; Omsetning {int(_omsetning or 0):,} NOK</div>
</div>
""", unsafe_allow_html=True)
else:
    st.markdown(f"""
<div class="om-cta">
  <div class="om-cta-txt">Legg inn ukens omsetning for å estimere potensiell gevinst</div>
  <div class="om-cta-sub">Finner du på norsk-tipping.no under Tippekupongen</div>
</div>
""", unsafe_allow_html=True)

# Omsetning input — always visible
_om_col, _ = st.columns([3, 7])
with _om_col:
    st.number_input(
        "Omsetning (NOK)",
        key="_om_raw",
        min_value=0,
        max_value=200_000_000,
        value=int(_omsetning or 0),
        step=500_000,
        on_change=_on_om_change,
        label_visibility="collapsed",
        help="Finn aktuell omsetning på norsk-tipping.no",
    )

st.markdown('<div class="gap-lg"></div>', unsafe_allow_html=True)

# ── Coupon + meta ─────────────────────────────────────────────────────────────
main_col, side_col = st.columns([7, 3])

with main_col:
    total_cost = total_rows * 2
    n_full = sum(1 for m in matches if len(picks[m.number]) == 3)
    n_half = sum(1 for m in matches if len(picks[m.number]) == 2)

    _cpn_label = SHORT_LABELS.get(coupon_key, "")
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
<div style="padding-top:2rem;">
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
    <span class="meta-stat-lbl">Poolverdi ratio</span>
    <span class="meta-stat-val {_pvr_sc}">{_pvr_s2}</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Poolverdi score</span>
    <span class="meta-stat-val">{_pvs_s}</span>
  </div>
  <div class="meta-stat">
    <span class="meta-stat-lbl">Verdivalg</span>
    <span class="meta-stat-val">{_n_val} av 12</span>
  </div>
</div>
""", unsafe_allow_html=True)

    st.markdown('<div class="gap-sm"></div>', unsafe_allow_html=True)

    if st.button("Lagre kupong", use_container_width=True, type="secondary"):
        from db.schema import init_db as _init_db2
        from db.coupon import get_coupon_matches, get_best_odds
        from db.history import save_prediction

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
            )
            saved += 1

        if saved == len(matches):
            st.success(f"Lagret {saved} kamper.")
        elif saved > 0:
            st.warning(f"{saved}/{len(matches)} lagret — {missing} mangler fixture_id.")
        else:
            st.error("Ingen lagret — kjør sync.py --seed-only.")

st.markdown('<div class="gap-lg"></div>', unsafe_allow_html=True)

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
