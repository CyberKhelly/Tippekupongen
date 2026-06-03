import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from models.match import Match
from analysis.probability import process_match
from analysis.classifier import classify_match
from analysis.optimizer import optimize_coupon
from data.coupon_week23_2026 import COUPONS

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tippekupongen",
    page_icon="⚽",
    layout="centered",
)

# ── Constants ──────────────────────────────────────────────────────────────────
COUPON_KEYS   = list(COUPONS.keys())
SHORT_LABELS  = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
DEADLINES     = {
    "midtuke": "Frist fredag 5. juni kl. 17:55",
    "lordag":  "Frist lørdag 6. juni kl. 14:55",
    "sondag":  "Frist søndag 7. juni kl. 15:55",
}
BUDGET_OPTS   = [32, 96, 192, 384]

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Tighten Streamlit's default padding */
.block-container { padding-top: 1.5rem !important; padding-bottom: 2rem !important; }

/* Radio buttons as pill-style selector */
div[data-testid="stRadio"] > label { font-weight: 700; font-size: 0.8rem;
    color: #666; text-transform: uppercase; letter-spacing: 1px; }
div[data-testid="stRadio"] > div { gap: 6px !important; }

/* Remove iframe border */
iframe { border: none !important; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_matches(coupon_key: str) -> list[Match]:
    matches = []
    for i, (home, away, oh, ou, ob) in enumerate(COUPONS[coupon_key]["matches"], 1):
        m = Match(number=i, home_team=home, away_team=away,
                  odds_h=oh, odds_u=ou, odds_b=ob)
        process_match(m)
        classify_match(m)
        matches.append(m)
    return matches


def short_note(m: Match, picks: list[str]) -> str:
    """One-line Norwegian explanation for a match's coverage decision."""
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
        gap = p1 - p2
        if gap <= 4:
            return f"{l1} og {l2} nesten like ({p1}% vs {p2}%)"
        return f"{l1} leder, men {l2} er reell ({p1}% vs {p2}%)"

    # Single — show recommended pick and confidence
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
    total_cost = total_rows * cost_per_row
    remaining  = budget - total_cost
    rem_color  = "#27ae60" if remaining >= 0 else "#e74c3c"

    coupon_label = COUPONS[coupon_key]["label"]

    def circle(label: str, selected: bool) -> str:
        if selected:
            bg, fg, bd = "#1a3a6e", "#fff", "#1a3a6e"
            shadow = "box-shadow:0 2px 6px rgba(26,58,110,.4);"
        else:
            bg, fg, bd = "#f0f2f6", "#bbb", "#dde"
            shadow = ""
        return (
            f'<div style="width:34px;height:34px;border-radius:50%;'
            f'background:{bg};color:{fg};border:2px solid {bd};{shadow}'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:12px;font-weight:800;flex-shrink:0;">{label}</div>'
        )

    _cov_bg    = {1: "transparent", 2: "#fffbea",        3: "#fff5f5"}
    _cov_label = {1: "",            2: "Halvdekk",        3: "Heldekkende"}
    _cov_color = {1: "transparent", 2: "#b8860b",         3: "#c0392b"}

    rows_html = ""
    for idx, m in enumerate(matches):
        mp       = picks[m.number]
        n        = len(mp)
        row_bg   = "#f9fbff" if idx % 2 == 0 else "#ffffff"
        if n > 1:
            row_bg = _cov_bg[n]

        note     = short_note(m, mp)
        note_col = "#888" if n == 1 else (_cov_color[n])

        badge = ""
        if n > 1:
            badge = (
                f'<span style="font-size:9px;font-weight:800;padding:2px 7px;'
                f'border-radius:10px;background:{_cov_color[n]};color:#fff;'
                f'white-space:nowrap;">{_cov_label[n]}</span>'
            )

        rows_html += (
            f'<div style="display:grid;grid-template-columns:22px 1fr auto;gap:10px;'
            f'padding:9px 16px;background:{row_bg};border-bottom:1px solid #e8eef8;'
            f'align-items:center;">'
            f'  <span style="color:#aaa;font-size:11px;font-weight:700;text-align:center;">{m.number}</span>'
            f'  <div style="min-width:0;">'
            f'    <div style="font-size:13px;font-weight:600;color:#1a1a2e;'
            f'         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{m.label}</div>'
            f'    <div style="font-size:10px;color:{note_col};margin-top:1px;">{note}</div>'
            f'    {"" if not badge else f"<div style=margin-top:3px;>{badge}</div>"}'
            f'  </div>'
            f'  <div style="display:flex;gap:4px;flex-shrink:0;">'
            f'    {circle("H","H" in mp)}{circle("U","U" in mp)}{circle("B","B" in mp)}'
            f'  </div>'
            f'</div>'
        )

    rem_sign = f"+{remaining:.0f}" if remaining >= 0 else f"{remaining:.0f}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0;box-sizing:border-box;}}</style>
</head><body style="font-family:'Segoe UI',Arial,sans-serif;background:transparent;">
<div style="border:3px solid #1a3a6e;border-radius:14px;overflow:hidden;
            box-shadow:0 6px 24px rgba(26,58,110,.18);">

  <div style="background:linear-gradient(135deg,#0f2555,#1a3a6e);
              padding:14px 20px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:18px;font-weight:900;letter-spacing:4px;color:#fff;">TIPPEKUPONGEN</div>
      <div style="font-size:11px;color:rgba(255,255,255,.6);margin-top:2px;">{coupon_label}</div>
    </div>
    <div style="text-align:right;">
      <div style="font-size:22px;font-weight:900;color:#fff;">{total_rows}</div>
      <div style="font-size:10px;color:rgba(255,255,255,.6);text-transform:uppercase;letter-spacing:1px;">rekker</div>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:22px 1fr auto;gap:10px;
              padding:6px 16px;background:#e8eef8;border-bottom:2px solid #1a3a6e;
              font-size:10px;font-weight:800;color:#1a3a6e;text-transform:uppercase;letter-spacing:1px;">
    <span style="text-align:center;">#</span>
    <span>Kamp</span>
    <div style="display:flex;gap:4px;">
      <span style="width:34px;text-align:center;">H</span>
      <span style="width:34px;text-align:center;">U</span>
      <span style="width:34px;text-align:center;">B</span>
    </div>
  </div>

  <div>{rows_html}</div>

  <div style="display:grid;grid-template-columns:repeat(3,1fr);
              background:#e8eef8;border-top:2px solid #1a3a6e;">
    <div style="padding:10px 14px;text-align:center;border-right:1px solid #c8d8ee;">
      <div style="font-size:10px;font-weight:700;color:#6688aa;text-transform:uppercase;letter-spacing:1px;">Rekker</div>
      <div style="font-size:20px;font-weight:900;color:#0f2555;">{total_rows}</div>
    </div>
    <div style="padding:10px 14px;text-align:center;border-right:1px solid #c8d8ee;">
      <div style="font-size:10px;font-weight:700;color:#6688aa;text-transform:uppercase;letter-spacing:1px;">Kostnad</div>
      <div style="font-size:20px;font-weight:900;color:#0f2555;">{total_cost:.0f} NOK</div>
    </div>
    <div style="padding:10px 14px;text-align:center;">
      <div style="font-size:10px;font-weight:700;color:#6688aa;text-transform:uppercase;letter-spacing:1px;">Rest</div>
      <div style="font-size:20px;font-weight:900;color:{rem_color};">{rem_sign} NOK</div>
    </div>
  </div>
</div>
</body></html>"""

    height = 60 + 35 + len(matches) * 62 + 56
    components.html(html, height=height, scrolling=False)


# ── Analysis table ─────────────────────────────────────────────────────────────

_CLS_STYLE = {
    "Banker":     "color:#155724;background-color:#d4edda;font-weight:bold",
    "Standard":   "color:#0c5460;background-color:#d1ecf1",
    "Half Cover": "color:#856404;background-color:#fff3cd",
    "Full Cover": "color:#721c24;background-color:#f8d7da",
    "Uncertain":  "color:#4a235a;background-color:#e8d5f5",
}

from analysis.classifier import classification_label

def _style_conf(val: float) -> str:
    if val >= 60: return "background-color:#d4edda;color:#155724;font-weight:bold"
    if val >= 52: return "background-color:#e8f5d0;color:#3a6b1a"
    if val >= 45: return "background-color:#fff3cd;color:#856404"
    return "background-color:#f8d7da;color:#721c24"

def render_analysis_table(matches: list[Match], picks: dict) -> None:
    _cov = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}
    rows = []
    for m in matches:
        n = len(picks[m.number])
        rows.append({
            "#":          m.number,
            "Kamp":       m.label,
            "H %":        round(m.prob_h * 100, 1),
            "U %":        round(m.prob_u * 100, 1),
            "B %":        round(m.prob_b * 100, 1),
            "Tips":       m.recommendation,
            "Konfidens":  round(m.confidence * 100, 1),
            "Dekning":    _cov[n],
        })
    df = pd.DataFrame(rows)

    def _cov_style(val: str) -> str:
        return {
            "Heldekkende": "background-color:#f8d7da;color:#721c24;font-weight:bold",
            "Halvdekk":    "background-color:#fff3cd;color:#856404;font-weight:bold",
            "Single":      "background-color:#d1ecf1;color:#0c5460",
        }.get(val, "")

    styled = (
        df.style
        .map(_cov_style,  subset=["Dekning"])
        .map(_style_conf, subset=["Konfidens"])
        .format({"H %": "{:.1f}%", "U %": "{:.1f}%",
                 "B %": "{:.1f}%", "Konfidens": "{:.1f}%"})
        .set_properties(subset=["Tips"], **{"font-weight": "bold", "text-align": "center"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("## ⚽ Tippekupongen")
st.caption("Uke 23 · 2026 · Odds er estimert — oppdater data/coupon_week23_2026.py for live-odds")

st.divider()

# ── Coupon type selector ───────────────────────────────────────────────────────
coupon_key = st.radio(
    "Kupong",
    options=COUPON_KEYS,
    format_func=lambda k: SHORT_LABELS[k],
    horizontal=True,
    label_visibility="collapsed",
    key="coupon_key",
)
st.caption(DEADLINES[coupon_key])

# ── Budget selector ────────────────────────────────────────────────────────────
budget = st.radio(
    "Budsjett (NOK)",
    options=BUDGET_OPTS,
    format_func=lambda x: f"{x} NOK",
    index=2,           # 192 NOK default
    horizontal=True,
    label_visibility="collapsed",
    key="budget",
)

st.divider()

# ── Auto-analyse ───────────────────────────────────────────────────────────────
matches = load_matches(coupon_key)
picks, total_rows = optimize_coupon(matches, float(budget))

# ── Summary strip ──────────────────────────────────────────────────────────────
n_full  = sum(1 for m in matches if len(picks[m.number]) == 3)
n_half  = sum(1 for m in matches if len(picks[m.number]) == 2)
n_single = sum(1 for m in matches if len(picks[m.number]) == 1)
avg_conf = sum(m.confidence for m in matches) / len(matches)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Heldekkende",  n_full)
c2.metric("Halvdekk",     n_half)
c3.metric("Single",       n_single)
c4.metric("Snitt konf.",  f"{avg_conf*100:.1f}%")

# ── Coupon card (hero element) ─────────────────────────────────────────────────
render_coupon_card(coupon_key, matches, picks, total_rows, budget)

# ── Kampanalyse (secondary, collapsed) ────────────────────────────────────────
with st.expander("Kampanalyse", expanded=False):
    render_analysis_table(matches, picks)
    st.markdown("""
**Forklaring:**

| Dekning | Rekker | Tildeles når |
|---|---|---|
| **Single** | ×1 | Klar favoritt eller budsjett brukt |
| **Halvdekk** | ×2 | To utfall nesten like sannsynlige |
| **Heldekkende** | ×3 | Alle tre utfall er reelle |

Optimizer velger kombinasjonen av heldekkende og halvdekk
som bruker budsjettet **fullt ut** — alltid.
    """)
