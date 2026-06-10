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

# ── Session state defaults ─────────────────────────────────────────────────────
if "coupon_key" not in st.session_state:
    st.session_state.coupon_key = COUPON_KEYS[0]
if "budget" not in st.session_state:
    st.session_state.budget = 192
if "strategy" not in st.session_state:
    st.session_state.strategy = DEFAULT_STRATEGY
if "omsetning" not in st.session_state:
    st.session_state.omsetning = None

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
    max-width: 1180px !important;
    margin: 0 auto !important;
    padding-top: 3.25rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    padding-bottom: 2rem !important;
}

/* ── Column layout ──────────────────────────────────────────────── */
/* Outer main split */
[data-testid="stHorizontalBlock"] {
    gap: 2rem !important;
    align-items: flex-start !important;
}
/*
 * Selector rows: any stHorizontalBlock nested inside another.
 * Keep display:flex (Streamlit's own model) but lock to one row with
 * equal-width columns. Streamlit ≥1.40 renamed column data-testid
 * from "column" to "stColumn"; both are listed for safety.
 */
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] {
    display: flex !important;
    flex-wrap: nowrap !important;
    gap: 5px !important;
    align-items: stretch !important;
}
/* Equal-width columns: flex-basis 0 + flex-grow 1 → all the same */
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] > [data-testid="column"] {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    width: 0 !important;
}
/* stButton Box wrapper: fill column */
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] [data-testid="stButton"] {
    width: 100% !important;
    display: block !important;
}
/* Buttons: fill column, no text wrap, slightly compact font */
.stApp [data-testid="stHorizontalBlock"] [data-testid="stHorizontalBlock"] button {
    min-width: 0 !important;
    width: 100% !important;
    white-space: nowrap !important;
    font-size: 0.8rem !important;
}

/* ── Logo mark ──────────────────────────────────────────────────── */
.logo-lockup {
    display: flex;
    align-items: center;
    gap: 14px;
}
/*
 * Football badge: circular dark-navy container with gold border and
 * glow. The SVG football icon inside is rendered inline in the header
 * HTML using <path d="M…L…Z"> with spaces (not commas) so Streamlit's
 * markdown parser does not misinterpret coordinate values.
 */
.logo-mark {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: radial-gradient(circle at 36% 30%, #1e3d7c 0%, #07101e 100%);
    border: 2.5px solid #f5c518;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    overflow: hidden;
    box-shadow:
        0 0 24px rgba(245,197,24,0.22),
        0 4px 16px rgba(0,0,0,0.65),
        inset 0 1px 0 rgba(255,255,255,0.09);
}

/* ── App wordmark ───────────────────────────────────────────────── */
.app-wordmark {
    font-size: 1.6rem;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: -0.3px;
    line-height: 1.05;
}
.app-wordmark .q { color: #f5c518; }

.app-meta-date {
    font-size: 0.78rem;
    color: #5a7a96;
    font-weight: 500;
    white-space: nowrap;
    padding-top: 4px;
}
.app-subtitle {
    font-size: 0.65rem;
    color: #2e4a64;
    margin-top: 2px;
}

/* ── Header row ─────────────────────────────────────────────────── */
.app-header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-bottom: 1rem;
    margin-bottom: 1.25rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}

/* ── Section labels ─────────────────────────────────────────────── */
.section-label {
    font-size: 0.6rem;
    font-weight: 700;
    color: #2e4a64;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    margin-bottom: 0.35rem;
    margin-top: 0.85rem;
}
.section-label:first-of-type { margin-top: 0; }

/* ── Deadline ────────────────────────────────────────────────────── */
.deadline-text {
    font-size: 0.72rem;
    color: #3aaa78;
    font-weight: 500;
    margin-top: 0.28rem;
    margin-bottom: 0;
}

/* ── Budget sub-labels ───────────────────────────────────────────── */
.budget-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 5px;
    margin-top: 3px;
    margin-bottom: 0.85rem;
}
.budget-sublabel {
    text-align: center;
    font-size: 0.61rem;
    color: #2e4a64;
    line-height: 1.4;
}
.budget-sublabel strong {
    display: block;
    color: #5a7a96;
    font-weight: 600;
    font-size: 0.63rem;
}

/* ── Buttons: selected = gold fill ──────────────────────────────── */
button[kind="primary"],
[data-testid="stBaseButton-primary"] {
    background-color: #f5c518 !important;
    color: #0b1623 !important;
    border: 2px solid #f5c518 !important;
    font-weight: 700 !important;
    width: 100% !important;
    transition: background 0.12s, box-shadow 0.12s !important;
}
button[kind="primary"]:hover,
[data-testid="stBaseButton-primary"]:hover {
    background-color: #f7d045 !important;
    border-color: #f7d045 !important;
    box-shadow: 0 0 14px rgba(245,197,24,.28) !important;
}
/* ── Buttons: unselected = ghost ─────────────────────────────────── */
button[kind="secondary"],
[data-testid="stBaseButton-secondary"] {
    background-color: rgba(255,255,255,0.04) !important;
    color: rgba(180,206,228,0.5) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    width: 100% !important;
}
button[kind="secondary"]:hover,
[data-testid="stBaseButton-secondary"]:hover {
    background-color: rgba(255,255,255,0.09) !important;
    color: rgba(180,206,228,0.85) !important;
    border-color: rgba(255,255,255,0.18) !important;
}

/* ── Summary strip ───────────────────────────────────────────────── */
.summary-strip {
    display: flex;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px;
    overflow: hidden;
    margin-top: 0.55rem;
}
.s-cell {
    flex: 1;
    padding: 8px 2px;
    text-align: center;
    border-right: 1px solid rgba(255,255,255,0.04);
}
.s-cell:last-child { border-right: none; }
.s-val {
    font-size: 0.95rem;
    font-weight: 800;
    color: #e0eaf4;
    line-height: 1.2;
}
.s-val.green { color: #2ecc71; }
.s-val.red   { color: #e74c3c; }
.s-key {
    font-size: 0.52rem;
    color: #2e4a64;
    text-transform: uppercase;
    letter-spacing: 0.9px;
    margin-top: 2px;
}

/* ── Right panel ─────────────────────────────────────────────────── */
.panel-title {
    font-size: 0.85rem;
    font-weight: 700;
    color: #c8d8e8;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding-bottom: 0.6rem;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    margin-bottom: 0.6rem;
}
.footnote {
    font-size: 0.75rem;
    color: #4a6a88;
    margin-top: 0.85rem;
    line-height: 1.65;
    padding-top: 0.7rem;
    border-top: 1px solid rgba(255,255,255,0.05);
}
.footnote strong { color: #6a90b0; }

/* Remove bottom border from last analysis row to prevent phantom line */
.analysis-tbl tbody tr:last-child td {
    border-bottom: none !important;
}

/* ── Misc ────────────────────────────────────────────────────────── */
hr { border-color: rgba(255,255,255,0.05) !important; margin: 0.75rem 0 !important; }
iframe { border: none !important; }

/* ── Estimert verdi panel ────────────────────────────────────────── */
.ev-panel {
    margin-top: 0.45rem;
    padding: 8px 12px 7px;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px;
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
}
.ev-header {
    font-size: 8px; font-weight: 700; color: #2e4a64;
    text-transform: uppercase; letter-spacing: 1.2px;
    display: flex; align-items: center; gap: 6px;
    margin-bottom: 6px;
}
.ev-strat-badge {
    font-size: 8px; font-weight: 700;
    padding: 1px 7px; border-radius: 3px;
}
.ev-grid {
    display: flex; gap: 0;
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 5px; overflow: hidden;
    margin-bottom: 6px;
}
.ev-cell {
    flex: 1; text-align: center;
    padding: 6px 2px;
    border-right: 1px solid rgba(255,255,255,0.04);
}
.ev-cell:last-child { border-right: none; }
.ev-val {
    font-size: 1.0rem; font-weight: 800; color: #e0eaf4; line-height: 1.2;
}
.ev-key {
    font-size: 0.48rem; color: #2e4a64;
    text-transform: uppercase; letter-spacing: 0.8px; margin-top: 2px;
}
.ev-payout {
    border-top: 1px solid rgba(255,255,255,0.04);
    padding-top: 5px; margin-top: 2px;
}
.ev-payout-label {
    font-size: 8px; color: #2e4a64; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.9px;
    margin-bottom: 4px;
}
.ev-payout-grid {
    display: flex; gap: 0;
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 4px; overflow: hidden;
}
.ev-payout-cell {
    flex: 1; text-align: center; padding: 4px 2px;
    border-right: 1px solid rgba(255,255,255,0.04);
}
.ev-payout-cell:last-child { border-right: none; }
.ev-payout-val {
    font-size: 0.85rem; font-weight: 800; color: #c8ddf0;
}
.ev-payout-key {
    font-size: 0.45rem; color: #2e4a64;
    text-transform: uppercase; letter-spacing: 0.7px; margin-top: 1px;
}
.ev-disclaimer {
    font-size: 7.5px; color: #1e3248; margin-top: 4px; font-style: italic;
}
.ev-warning {
    margin-top: 5px; font-size: 8.5px; color: #c8960e;
    padding: 3px 7px; background: rgba(200,150,14,0.06); border-radius: 3px;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

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


def short_note(m: Match, picks: list[str]) -> str:
    h = round(m.prob_h * 100)
    u = round(m.prob_u * 100)
    b = round(m.prob_b * 100)
    n = len(picks)
    if n == 3:
        return f"Åpen kamp — {h}% / {u}% / {b}%"
    if n == 2:
        probs = sorted(
            [("H", m.prob_h, h), ("U", m.prob_u, u), ("B", m.prob_b, b)],
            key=lambda x: x[1], reverse=True,
        )
        l1, _, p1 = probs[0]
        l2, _, p2 = probs[1]
        if p1 - p2 <= 4:
            return f"{l1} og {l2} nesten like ({p1}% vs {p2}%)"
        return f"{l1} leder, men {l2} er reell ({p1}% vs {p2}%)"
    probs = sorted(
        [("H", m.prob_h, h), ("U", m.prob_u, u), ("B", m.prob_b, b)],
        key=lambda x: x[1], reverse=True,
    )
    l, _, p = probs[0]
    return f"{l} — {p}%"


def render_coupon_card(
    coupon_key: str,
    matches: list[Match],
    picks: dict,
    total_rows: int,
    budget: int,
    cost_per_row: float = 1.0,
) -> None:
    total_cost   = total_rows * cost_per_row
    remaining    = budget - total_cost
    rem_color    = "#2ecc71" if remaining >= 0 else "#e74c3c"
    coupon_label = COUPONS[coupon_key]["label"]

    def circle(label: str, selected: bool) -> str:
        if selected:
            bg, fg, bd = "#1a3a6e", "#fff", "#1a3a6e"
            shadow = "box-shadow:0 1px 5px rgba(26,58,110,.5);"
        else:
            bg, fg, bd = "#edf1f7", "#b0bac8", "#d8e0ea"
            shadow = ""
        return (
            f'<div style="width:28px;height:28px;border-radius:50%;'
            f'background:{bg};color:{fg};border:2px solid {bd};{shadow}'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:10.5px;font-weight:800;flex-shrink:0;">{label}</div>'
        )

    _cov_bg = {
        1: "transparent",
        2: "#fffcf0",
        3: "#fff8f8",
    }
    _note_col = {
        1: "#9aacbe",
        2: "#a07a10",
        3: "#a03030",
    }

    rows_html = ""
    for idx, m in enumerate(matches):
        mp     = picks[m.number]
        n      = len(mp)
        row_bg = "#f8fbff" if idx % 2 == 0 else "#ffffff"
        if n > 1:
            row_bg = _cov_bg[n]

        note     = short_note(m, mp)
        note_col = _note_col[n]

        rows_html += (
            f'<div style="display:grid;grid-template-columns:18px 1fr auto;gap:8px;'
            f'padding:6px 13px;background:{row_bg};border-bottom:1px solid #eaf0f8;'
            f'align-items:center;min-height:0;">'
            f'  <span style="color:#b0bec8;font-size:9.5px;font-weight:700;'
            f'        text-align:center;line-height:1;">{m.number}</span>'
            f'  <div style="min-width:0;overflow:hidden;">'
            f'    <div style="font-size:12px;font-weight:600;color:#1a1e2e;'
            f'         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'         line-height:1.3;">{m.label}</div>'
            f'    <div style="font-size:9px;color:{note_col};margin-top:1px;'
            f'         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'
            f'         line-height:1.3;">{note}</div>'
            f'  </div>'
            f'  <div style="display:flex;gap:3px;flex-shrink:0;">'
            f'    {circle("H","H" in mp)}{circle("U","U" in mp)}{circle("B","B" in mp)}'
            f'  </div>'
            f'</div>'
        )

    rem_sign = f"+{remaining:.0f}" if remaining >= 0 else f"{remaining:.0f}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:'Segoe UI',system-ui,Arial,sans-serif;background:transparent;}}
</style>
</head><body>
<div style="border:2px solid #19356a;border-radius:12px;overflow:hidden;
            box-shadow:0 6px 28px rgba(0,0,0,.45);">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#0d2050 0%,#1a3a6e 100%);
              padding:11px 15px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:14.5px;font-weight:900;letter-spacing:3.5px;
                  color:#fff;line-height:1;">TIPPE<span style="color:#f5c518;">Q</span>PONGEN</div>
      <div style="font-size:9.5px;color:rgba(255,255,255,.45);margin-top:3px;">{coupon_label}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:21px;font-weight:900;color:#fff;line-height:1;">{total_rows}</div>
      <div style="font-size:8.5px;color:rgba(255,255,255,.45);text-transform:uppercase;
                  letter-spacing:1px;margin-top:2px;">rekker</div>
    </div>
  </div>

  <!-- Column header -->
  <div style="display:grid;grid-template-columns:18px 1fr auto;gap:8px;
              padding:5px 13px;background:#dde6f2;border-bottom:1.5px solid #19356a;
              font-size:8.5px;font-weight:800;color:#19356a;text-transform:uppercase;
              letter-spacing:1.2px;">
    <span style="text-align:center;">#</span>
    <span>Kamp</span>
    <div style="display:flex;gap:3px;">
      <span style="width:28px;text-align:center;">H</span>
      <span style="width:28px;text-align:center;">U</span>
      <span style="width:28px;text-align:center;">B</span>
    </div>
  </div>

  <!-- Match rows -->
  <div>{rows_html}</div>

  <!-- Footer -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);
              background:#dde6f2;border-top:1.5px solid #19356a;">
    <div style="padding:8px 10px;text-align:center;border-right:1px solid #c2d0e4;">
      <div style="font-size:8.5px;font-weight:700;color:#5a78a0;text-transform:uppercase;
                  letter-spacing:1px;">Rekker</div>
      <div style="font-size:17px;font-weight:900;color:#0d2050;margin-top:1px;">{total_rows}</div>
    </div>
    <div style="padding:8px 10px;text-align:center;border-right:1px solid #c2d0e4;">
      <div style="font-size:8.5px;font-weight:700;color:#5a78a0;text-transform:uppercase;
                  letter-spacing:1px;">Kostnad</div>
      <div style="font-size:17px;font-weight:900;color:#0d2050;margin-top:1px;">{total_cost:.0f} NOK</div>
    </div>
    <div style="padding:8px 10px;text-align:center;">
      <div style="font-size:8.5px;font-weight:700;color:#5a78a0;text-transform:uppercase;
                  letter-spacing:1px;">Rest</div>
      <div style="font-size:17px;font-weight:900;color:{rem_color};margin-top:1px;">{rem_sign} NOK</div>
    </div>
  </div>

</div>
</body></html>"""

    # row_h: 12px pad + (12px×1.3 name + 1px gap + 9px×1.3 note) + 1px border = 42px
    # header 52px, col-header 22px, footer 52px (includes 1.5px border-top + 2px outer border)
    row_h  = 42
    height = 52 + 22 + len(matches) * row_h + 52
    components.html(html, height=height, scrolling=False)


def render_analysis_table(matches: list[Match], picks: dict) -> None:
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

    def conf_colors(v: float):
        for thr, bg, fg in _conf_tiers:
            if v >= thr:
                return bg, fg
        return _conf_tiers[-1][1], _conf_tiers[-1][2]

    # Single source-of-truth for shared style fragments — no string substitution tricks.
    _th_base = ("font-size:9px;font-weight:700;color:#2e4a64;text-transform:uppercase;"
                "letter-spacing:1.3px;border-bottom:1px solid rgba(255,255,255,0.07);"
                "white-space:nowrap;background:rgba(255,255,255,0.04);padding:8px 9px;")
    _td_base = "padding:6px 9px;border-bottom:1px solid rgba(255,255,255,0.03);font-size:11px;"
    _badge   = "font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;white-space:nowrap;"

    # Build exactly 9 <th> cells — alignment appended per column, never via .replace()
    thead = (
        f'<tr>'
        f'<th style="{_th_base}text-align:center;">#</th>'
        f'<th style="{_th_base}text-align:left;">Kamp</th>'
        f'<th style="{_th_base}text-align:right;">H</th>'
        f'<th style="{_th_base}text-align:right;">U</th>'
        f'<th style="{_th_base}text-align:right;">B</th>'
        f'<th style="{_th_base}text-align:center;">Tips</th>'
        f'<th style="{_th_base}text-align:center;">Konf.</th>'
        f'<th style="{_th_base}text-align:center;">Dekning</th>'
        f'<th style="{_th_base}text-align:right;" title="Verdiindeks: modell/folket for anbefalt utfall. 1.00=nøytralt, >1.25=god verdi">VI</th>'
        f'</tr>'
    )

    _src_badge = {
        "nt_expert":   ('<span style="font-size:8px;font-weight:700;padding:1px 5px;border-radius:3px;'
                        'background:#1a2d1a;color:#4a9a4a;margin-left:5px;vertical-align:middle;">Tips</span>'),
        "placeholder": ('<span style="font-size:8px;font-weight:700;padding:1px 5px;border-radius:3px;'
                        'background:#1a1a1a;color:#444;margin-left:5px;vertical-align:middle;">—</span>'),
    }

    def _src_tag(src: str) -> str:
        if not src or src == "pinnacle":
            return ""
        if src in _src_badge:
            return _src_badge[src]
        # Other bookmakers (betsson, unibet_se, etc.) → "Alt" badge
        return ('<span style="font-size:8px;font-weight:700;padding:1px 5px;border-radius:3px;'
                'background:#1a1e2e;color:#5a7a96;margin-left:5px;vertical-align:middle;">Alt</span>')

    rows_html = ""
    for i, m in enumerate(matches):
        n        = len(picks[m.number])
        cov_lbl  = _cov[n]
        conf_val = round(m.confidence * 100, 1)
        cbg, cfg = conf_colors(conf_val)
        vbg, vfg = _cov_colors[cov_lbl]
        row_bg   = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"
        src_tag  = _src_tag(m.odds_source)

        # Value index for the recommended pick (model_prob / public_prob)
        _vi_val = None
        if m.has_public_tips and m.recommendation:
            _prob = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}.get(m.recommendation)
            _pub  = {"H": m.pub_prob_h, "U": m.pub_prob_u, "B": m.pub_prob_b}.get(m.recommendation)
            _vi_val = compute_value_index(_prob or 0, _pub)
        if _vi_val is not None:
            _vi_color = "#3aaa78" if _vi_val >= 1.25 else "#74cc9a" if _vi_val >= 1.0 else "#e0956a" if _vi_val >= 0.80 else "#e07a5f"
            _vi_str   = f"{_vi_val:.2f}×"
        else:
            _vi_color = "#2e4a64"
            _vi_str   = "—"

        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="{_td_base}color:#2e4a64;text-align:center;">{m.number}</td>'
            f'<td style="{_td_base}color:#c8ddf0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;">{m.label}{src_tag}</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_h*100,1)}%</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_u*100,1)}%</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_b*100,1)}%</td>'
            f'<td style="{_td_base}text-align:center;font-weight:800;color:#f5c518;">{m.recommendation}</td>'
            f'<td style="{_td_base}text-align:center;"><span style="{_badge}background:{cbg};color:{cfg};">{conf_val:.1f}%</span></td>'
            f'<td style="{_td_base}text-align:center;"><span style="{_badge}background:{vbg};color:{vfg};">{cov_lbl}</span></td>'
            f'<td style="{_td_base}text-align:right;font-weight:700;color:{_vi_color};font-size:10px;" title="Verdiindeks: modell/folket for valgt utfall">{_vi_str}</td>'
            f'</tr>'
        )

    html = (
        '<div style="overflow-x:auto;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">'
        '<table class="analysis-tbl" style="width:100%;border-collapse:collapse;'
        'font-family:\'Segoe UI\',system-ui,Arial,sans-serif;">'
        f'<thead>{thead}</thead>'
        f'<tbody>{rows_html}</tbody>'
        '</table></div>'
    )
    st.markdown(html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════

# ── Full-width header ──────────────────────────────────────────────────────────
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

# ── Two-panel split ────────────────────────────────────────────────────────────
left_col, right_col = st.columns([5, 6])

# ╔══════════════════════════════════════════════════════╗
# ║  LEFT PANEL — controls + coupon                      ║
# ╚══════════════════════════════════════════════════════╝
with left_col:

    # Coupon type selector
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
        f'<div class="deadline-text">● Frist: {DEADLINES[coupon_key]} · 12 kamper</div>',
        unsafe_allow_html=True,
    )

    # Budget selector
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
            f'<div class="budget-sublabel"><strong>{BUDGET_LABELS[amt]}</strong>'
            f'{BUDGET_ROWS[amt]} rek.</div>'
            for amt in BUDGET_OPTS
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # Strategy selector
    st.markdown('<div class="section-label">Strategi</div>', unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)
    for col, key in zip([s1, s2, s3, s4], _STRATEGY_KEYS):
        with col:
            active = st.session_state.strategy == key
            if st.button(_STRATEGY_LABELS[key], key=f"strategy_{key}",
                         use_container_width=True,
                         type="primary" if active else "secondary"):
                st.session_state.strategy = key
                st.rerun()

    budget   = st.session_state.budget
    strategy = st.session_state.strategy

    # Compute
    matches = load_matches(coupon_key)
    picks, total_rows = optimize_coupon(matches, float(budget), strategy=strategy)
    pvs = compute_pool_value_score(matches, picks)

    # Pool value analytics (deterministic)
    p_win   = compute_p_win(matches, picks)
    pv_ratio = compute_pool_value_ratio(matches, picks)

    # Coupon card (hero)
    render_coupon_card(coupon_key, matches, picks, total_rows, budget)

    # Summary strip
    n_full     = sum(1 for m in matches if len(picks[m.number]) == 3)
    n_half     = sum(1 for m in matches if len(picks[m.number]) == 2)
    n_single   = sum(1 for m in matches if len(picks[m.number]) == 1)
    total_cost = total_rows * 1.0
    remaining  = budget - total_cost
    rem_cls    = "green" if remaining >= 0 else "red"
    rem_str    = f"+{remaining:.0f}" if remaining >= 0 else f"{remaining:.0f}"

    if pvs is not None:
        _pvs_color = "#3aaa78" if pvs > 0 else "#e07a5f"
        _pvs_str   = f"{pvs:+.1f}pp"
        pvs_cell   = (
            f'<div class="s-cell">'
            f'<div class="s-val" style="color:{_pvs_color};">{_pvs_str}</div>'
            f'<div class="s-key">Poolverdi</div>'
            f'</div>'
        )
    else:
        pvs_cell = (
            '<div class="s-cell">'
            '<div class="s-val" style="color:#2e4a64;">—</div>'
            '<div class="s-key">Poolverdi</div>'
            '</div>'
        )

    st.markdown(f"""
<div class="summary-strip">
  <div class="s-cell"><div class="s-val">{n_full}</div><div class="s-key">Heldekkende</div></div>
  <div class="s-cell"><div class="s-val">{n_half}</div><div class="s-key">Halvdekk</div></div>
  <div class="s-cell"><div class="s-val">{n_single}</div><div class="s-key">Single</div></div>
  <div class="s-cell"><div class="s-val">{total_rows}</div><div class="s-key">Rekker</div></div>
  <div class="s-cell"><div class="s-val">{total_cost:.0f} NOK</div><div class="s-key">Kostnad</div></div>
  <div class="s-cell"><div class="s-val {rem_cls}">{rem_str} NOK</div><div class="s-key">Rest</div></div>
  {pvs_cell}
</div>
""", unsafe_allow_html=True)

    # ── Estimert verdi panel ───────────────────────────────────────────────────
    _strat_bg, _strat_fg = _STRATEGY_COLORS[strategy]
    _strat_name = _STRATEGY_LABELS[strategy]

    _pwin_str = f"{p_win * 100:.2f}%"
    _pwin_col = "#3aaa78" if p_win >= 0.05 else "#c8960e" if p_win >= 0.01 else "#e07a5f"

    _pvr_str = f"{pv_ratio:.2f}×" if pv_ratio is not None else "—"
    _pvr_col = "#3aaa78" if (pv_ratio or 0) >= 1.0 else "#e07a5f"

    _n_val_picks = sum(
        1 for m in matches
        if m.has_public_tips and m.recommendation and
        ({"H": m.value_h, "U": m.value_u, "B": m.value_b}.get(m.recommendation) or 0) > 0
    )

    # Payout simulation (only when omsetning is set)
    _omsetning = st.session_state.omsetning
    _sim = None
    if _omsetning and _omsetning > 0:
        _sim = simulate_payout(matches, picks, total_rows, float(_omsetning))

    # Warning if coupon is too crowd-aligned
    _warning_html = ""
    if pv_ratio is not None and pv_ratio < 0.85:
        _warning_html = (
            '<div class="ev-warning">'
            '⚠ Kupongen er nær folkets valg — vurder Verdi eller Jackpot strategi'
            '</div>'
        )

    _payout_html = ""
    if _sim and _sim.get("n_winning_sims", 0) > 0:
        _payout_html = f"""
<div class="ev-payout">
  <div class="ev-payout-label">Estimert utdeling ved 12/12</div>
  <div class="ev-payout-grid">
    <div class="ev-payout-cell">
      <div class="ev-payout-val">{_sim['min']:,} kr</div>
      <div class="ev-payout-key">Min</div>
    </div>
    <div class="ev-payout-cell">
      <div class="ev-payout-val">{_sim['median']:,} kr</div>
      <div class="ev-payout-key">Median</div>
    </div>
    <div class="ev-payout-cell">
      <div class="ev-payout-val">{_sim['max']:,} kr</div>
      <div class="ev-payout-key">Max</div>
    </div>
  </div>
  <div class="ev-disclaimer">
    * Estimat basert på omsetning {_omsetning:,.0f} NOK og 52% premieandel.
    Faktisk utdeling kan avvike vesentlig.
  </div>
</div>"""

    st.markdown(f"""
<div class="ev-panel">
  <div class="ev-header">
    Estimert verdi
    <span class="ev-strat-badge" style="background:{_strat_bg};color:{_strat_fg};">
      {_strat_name}
    </span>
  </div>
  <div class="ev-grid">
    <div class="ev-cell">
      <div class="ev-val" style="color:{_pwin_col};">{_pwin_str}</div>
      <div class="ev-key">Sjanse 12/12</div>
    </div>
    <div class="ev-cell">
      <div class="ev-val" style="color:{_pvr_col};">{_pvr_str}</div>
      <div class="ev-key">Poolverdi ratio</div>
    </div>
    <div class="ev-cell">
      <div class="ev-val">{_n_val_picks}</div>
      <div class="ev-key">Verdivalg</div>
    </div>
  </div>
  {_payout_html}
  {_warning_html}
</div>
""", unsafe_allow_html=True)

    # ── Optional omsetning input ───────────────────────────────────────────────
    with st.expander("Legg inn omsetning for utdelingsestimat", expanded=False):
        _om_input = st.number_input(
            "Omsetning (NOK)",
            min_value=0,
            max_value=200_000_000,
            value=int(st.session_state.omsetning or 0),
            step=500_000,
            help="Finn aktuell omsetning på Norsk Tipping sin nettside. Brukes til å estimere utdeling.",
        )
        st.session_state.omsetning = _om_input if _om_input > 0 else None

    # ── Save coupon snapshot ───────────────────────────────────────────────────
    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    if st.button("💾 Lagre kupong", use_container_width=True, type="secondary"):
        from db.schema import init_db
        from db.coupon import get_coupon_matches, get_best_odds
        from db.history import save_prediction

        init_db()
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
            st.warning(f"{saved} av {len(matches)} lagret. {missing} kamp(er) mangler fixture_id — kjør sync først.")
        else:
            st.error("Kunne ikke lagre: kupongen er ikke i databasen ennå. Kjør `python sync.py --seed-only` først.")

# ╔══════════════════════════════════════════════════════╗
# ║  RIGHT PANEL — analysis table (always visible)       ║
# ╚══════════════════════════════════════════════════════╝
with right_col:
    st.markdown('<div class="panel-title">Kampanalyse</div>', unsafe_allow_html=True)
    render_analysis_table(matches, picks)
    st.markdown("""
<div class="footnote">
<strong>Dekning:</strong> Single ×1 &nbsp;·&nbsp; Halvdekk ×2 &nbsp;·&nbsp; Heldekkende ×3<br>
<strong>Trygghet:</strong> Sannsynlighet for det sterkeste enkeltutfallet — ikke for at hele kupongen vinner.
</div>
""", unsafe_allow_html=True)
