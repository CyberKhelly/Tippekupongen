import streamlit as st
import streamlit.components.v1 as components

from models.match import Match
from analysis.probability import process_match
from analysis.classifier import classify_match
from analysis.optimizer import optimize_coupon
from analysis.classifier import classification_label
from data.coupon_week23_2026 import COUPONS

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="TippeQpongen",
    page_icon="⚽",
    layout="centered",
)

# ── Constants ──────────────────────────────────────────────────────────────────
COUPON_KEYS   = list(COUPONS.keys())
SHORT_LABELS  = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
DEADLINES     = {
    "midtuke": "Fre. 5. juni · 17:55",
    "lordag":  "Lør. 6. juni · 14:55",
    "sondag":  "Søn. 7. juni · 15:55",
}
BUDGET_OPTS   = [32, 96, 192, 384]
BUDGET_LABELS = {32: "Enkel", 96: "Balansert", 192: "Anbefalt", 384: "Høy dekning"}
BUDGET_ROWS   = {32: 32, 96: 96, 192: 192, 384: 384}  # optimal rows for 12 matches @ 1 NOK/row

# ── Session state defaults ─────────────────────────────────────────────────────
if "coupon_key" not in st.session_state:
    st.session_state.coupon_key = COUPON_KEYS[0]
if "budget" not in st.session_state:
    st.session_state.budget = 192

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── App background ─────────────────────────────────────────────── */
.stApp { background-color: #0d1b2a; }
[data-testid="stHeader"] {
    background-color: #0d1b2a !important;
    border-bottom: 1px solid rgba(255,255,255,0.05) !important;
}
.block-container {
    padding-top: 4rem !important;
    padding-bottom: 3rem !important;
    max-width: 700px !important;
}

/* ── App header ─────────────────────────────────────────────────── */
.app-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 0.15rem;
}
.app-title {
    font-size: 1.75rem;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: 0.5px;
    line-height: 1.2;
}
.app-week {
    font-size: 0.85rem;
    color: #7a9ab8;
    font-weight: 500;
}
.app-subtitle {
    font-size: 0.72rem;
    color: #4a6a88;
    margin-bottom: 1.75rem;
    letter-spacing: 0.3px;
}

/* ── Section labels ─────────────────────────────────────────────── */
.section-label {
    font-size: 0.67rem;
    font-weight: 700;
    color: #4a6a88;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    margin-bottom: 0.4rem;
}
.section-gap { margin-top: 1.1rem; }

/* ── Deadline ───────────────────────────────────────────────────── */
.deadline-text {
    font-size: 0.78rem;
    color: #7a9ab8;
    margin-top: 0.3rem;
    margin-bottom: 0.2rem;
}

/* ── Budget sub-labels (rendered as a single HTML grid row) ──────── */
.budget-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 8px;
    margin-top: 4px;
    margin-bottom: 1.1rem;
}
.budget-sublabel {
    text-align: center;
    font-size: 0.67rem;
    color: #4a6a88;
    line-height: 1.4;
}
.budget-sublabel strong {
    display: block;
    color: #7a9ab8;
    font-weight: 600;
}

/* ── Primary button = selected (gold) ───────────────────────────── */
button[kind="primary"] {
    background-color: #f5c518 !important;
    color: #0d1b2a !important;
    border: 2px solid #f5c518 !important;
    font-weight: 700 !important;
    transition: all 0.15s ease !important;
}
button[kind="primary"]:hover {
    background-color: #f7cf45 !important;
    border-color: #f7cf45 !important;
    box-shadow: 0 2px 12px rgba(245,197,24,.3) !important;
}
button[kind="primary"]:focus:not(:active) {
    box-shadow: 0 0 0 3px rgba(245,197,24,.35) !important;
}

/* ── Secondary button = unselected (ghost) ──────────────────────── */
button[kind="secondary"] {
    background-color: rgba(255,255,255,0.05) !important;
    color: rgba(200,216,232,0.65) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
}
button[kind="secondary"]:hover {
    background-color: rgba(255,255,255,0.1) !important;
    color: rgba(200,216,232,0.9) !important;
    border-color: rgba(255,255,255,0.22) !important;
}

/* ── Summary strip ──────────────────────────────────────────────── */
.summary-strip {
    display: flex;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    overflow: hidden;
    margin-top: 0.65rem;
    margin-bottom: 0.75rem;
}
.s-cell {
    flex: 1;
    padding: 9px 4px;
    text-align: center;
    border-right: 1px solid rgba(255,255,255,0.06);
}
.s-cell:last-child { border-right: none; }
.s-val {
    font-size: 1.05rem;
    font-weight: 800;
    color: #ffffff;
    line-height: 1.2;
}
.s-val.green { color: #2ecc71; }
.s-val.red   { color: #e74c3c; }
.s-key {
    font-size: 0.58rem;
    color: #4a6a88;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-top: 2px;
}

/* ── Expander ───────────────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary p,
.streamlit-expanderHeader p {
    color: #7a9ab8 !important;
    font-size: 0.85rem !important;
}
[data-testid="stExpander"] p     { color: #c8d8e8 !important; }
[data-testid="stExpander"] table { color: #c8d8e8; }
[data-testid="stExpander"] th    { color: #7a9ab8 !important; }
[data-testid="stExpander"] strong { color: #ddeeff !important; }

/* ── Column gap ─────────────────────────────────────────────────── */
[data-testid="stHorizontalBlock"] { gap: 8px !important; }

/* ── Divider ────────────────────────────────────────────────────── */
hr { border-color: rgba(255,255,255,0.07) !important; margin: 1rem 0 !important; }

/* ── iframes ────────────────────────────────────────────────────── */
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

    _cov_bg    = {1: "transparent", 2: "#fffbea",    3: "#fff5f5"}
    _cov_label = {1: "",            2: "Halvdekk",   3: "Heldekkende"}
    _cov_color = {1: "transparent", 2: "#b8860b",    3: "#c0392b"}

    rows_html = ""
    for idx, m in enumerate(matches):
        mp     = picks[m.number]
        n      = len(mp)
        row_bg = "#f9fbff" if idx % 2 == 0 else "#ffffff"
        if n > 1:
            row_bg = _cov_bg[n]

        note     = short_note(m, mp)
        note_col = "#888" if n == 1 else _cov_color[n]

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
            box-shadow:0 8px 32px rgba(0,0,0,.4);">

  <div style="background:linear-gradient(135deg,#0f2555,#1a3a6e);
              padding:14px 20px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:18px;font-weight:900;letter-spacing:4px;color:#fff;">TIPPEQPONGEN</div>
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


def render_analysis_table(matches: list[Match], picks: dict) -> None:
    _cov = {1: "Single", 2: "Halvdekk", 3: "Heldekkende"}

    _conf_style = [
        (60, "#0f2d14", "#4caf6e"),   # val >= 60: dark green bg, green text
        (52, "#162a14", "#7bc87a"),   # val >= 52
        (45, "#2d2000", "#e6a817"),   # val >= 45: amber
        ( 0, "#2d0f0f", "#d46a6a"),   # val <  45: red
    ]

    _cov_style = {
        "Single":      ("#0d1f36", "#7ab8e0"),
        "Halvdekk":    ("#2d2000", "#e6a817"),
        "Heldekkende": ("#2d0f0f", "#d46a6a"),
    }

    def conf_colors(val: float):
        for threshold, bg, fg in _conf_style:
            if val >= threshold:
                return bg, fg
        return _conf_style[-1][1], _conf_style[-1][2]

    th = (
        "color:#4a6a88;font-size:10px;font-weight:700;text-transform:uppercase;"
        "letter-spacing:1px;padding:8px 10px;border-bottom:1px solid rgba(255,255,255,0.1);"
        "white-space:nowrap;"
    )
    badge = "font-size:10px;font-weight:700;padding:2px 8px;border-radius:5px;white-space:nowrap;"

    rows_html = ""
    for i, m in enumerate(matches):
        n        = len(picks[m.number])
        cov_lbl  = _cov[n]
        conf_val = round(m.confidence * 100, 1)
        cbg, cfg = conf_colors(conf_val)
        vbg, vfg = _cov_style[cov_lbl]
        row_bg   = "rgba(255,255,255,0.03)" if i % 2 == 0 else "transparent"

        td = f"color:#c8d8e8;padding:7px 10px;border-bottom:1px solid rgba(255,255,255,0.04);"

        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'  <td style="{td}color:#5a7a96;text-align:center;">{m.number}</td>'
            f'  <td style="{td}color:#ddeeff;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{m.label}</td>'
            f'  <td style="{td}text-align:right;">{round(m.prob_h*100,1)}%</td>'
            f'  <td style="{td}text-align:right;">{round(m.prob_u*100,1)}%</td>'
            f'  <td style="{td}text-align:right;">{round(m.prob_b*100,1)}%</td>'
            f'  <td style="{td}text-align:center;font-weight:800;color:#f5c518;">{m.recommendation}</td>'
            f'  <td style="{td}text-align:center;padding-left:4px;padding-right:4px;">'
            f'    <span style="{badge}background:{cbg};color:{cfg};">{conf_val:.1f}%</span>'
            f'  </td>'
            f'  <td style="{td}text-align:center;padding-left:4px;padding-right:10px;">'
            f'    <span style="{badge}background:{vbg};color:{vfg};">{cov_lbl}</span>'
            f'  </td>'
            f'</tr>'
        )

    table_html = f"""
<div style="overflow-x:auto;border-radius:8px;border:1px solid rgba(255,255,255,0.07);margin-bottom:1rem;">
<table style="width:100%;border-collapse:collapse;font-family:'Segoe UI',Arial,sans-serif;font-size:12px;">
  <thead>
    <tr style="background:rgba(255,255,255,0.06);">
      <th style="{th}text-align:center;">#</th>
      <th style="{th}text-align:left;">Kamp</th>
      <th style="{th}text-align:right;">H</th>
      <th style="{th}text-align:right;">U</th>
      <th style="{th}text-align:right;">B</th>
      <th style="{th}text-align:center;">Tips</th>
      <th style="{th}text-align:center;">Konf.</th>
      <th style="{th}text-align:center;">Dekning</th>
    </tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
</div>
"""
    st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════

# ── Header ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
  <span class="app-title">⚽ TippeQpongen</span>
  <span class="app-week">Uke 23 · 2026</span>
</div>
<div class="app-subtitle">Basert på estimerte odds · oppdateres ukentlig</div>
""", unsafe_allow_html=True)

# ── Coupon selector ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-label">Kupong</div>', unsafe_allow_html=True)

tab_cols = st.columns(3)
for col, key in zip(tab_cols, COUPON_KEYS):
    with col:
        is_active = st.session_state.coupon_key == key
        if st.button(
            SHORT_LABELS[key],
            key=f"tab_{key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.coupon_key = key
            st.rerun()

coupon_key = st.session_state.coupon_key
st.markdown(
    f'<div class="deadline-text">🕐 Frist: {DEADLINES[coupon_key]} &nbsp;·&nbsp; 12 kamper</div>',
    unsafe_allow_html=True,
)

# ── Budget selector ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-label section-gap">Budsjett</div>', unsafe_allow_html=True)

budget_cols = st.columns(4)
for col, amt in zip(budget_cols, BUDGET_OPTS):
    with col:
        is_active = st.session_state.budget == amt
        if st.button(
            f"{amt} NOK",
            key=f"budget_{amt}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.budget = amt
            st.rerun()

st.markdown(
    '<div class="budget-row">'
    + "".join(
        f'<div class="budget-sublabel">'
        f'<strong>{BUDGET_LABELS[amt]}</strong>'
        f'{BUDGET_ROWS[amt]} rek.'
        f'</div>'
        for amt in BUDGET_OPTS
    )
    + "</div>",
    unsafe_allow_html=True,
)

budget = st.session_state.budget

# ── Compute ─────────────────────────────────────────────────────────────────────
matches = load_matches(coupon_key)
picks, total_rows = optimize_coupon(matches, float(budget))

# ── Coupon card (hero) ─────────────────────────────────────────────────────────
render_coupon_card(coupon_key, matches, picks, total_rows, budget)

# ── Summary strip ──────────────────────────────────────────────────────────────
n_full     = sum(1 for m in matches if len(picks[m.number]) == 3)
n_half     = sum(1 for m in matches if len(picks[m.number]) == 2)
n_single   = sum(1 for m in matches if len(picks[m.number]) == 1)
total_cost = total_rows * 1.0
remaining  = budget - total_cost
rem_cls    = "green" if remaining >= 0 else "red"
rem_str    = f"+{remaining:.0f}" if remaining >= 0 else f"{remaining:.0f}"

st.markdown(f"""
<div class="summary-strip">
  <div class="s-cell">
    <div class="s-val">{n_full}</div>
    <div class="s-key">Heldekkende</div>
  </div>
  <div class="s-cell">
    <div class="s-val">{n_half}</div>
    <div class="s-key">Halvdekk</div>
  </div>
  <div class="s-cell">
    <div class="s-val">{n_single}</div>
    <div class="s-key">Single</div>
  </div>
  <div class="s-cell">
    <div class="s-val">{total_rows}</div>
    <div class="s-key">Rekker</div>
  </div>
  <div class="s-cell">
    <div class="s-val">{total_cost:.0f} NOK</div>
    <div class="s-key">Kostnad</div>
  </div>
  <div class="s-cell">
    <div class="s-val {rem_cls}">{rem_str} NOK</div>
    <div class="s-key">Rest</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Analysis expander ──────────────────────────────────────────────────────────
st.markdown('<div style="margin-top:0.5rem;"></div>', unsafe_allow_html=True)
with st.expander("Se kampanalyse", expanded=False):
    render_analysis_table(matches, picks)
    st.markdown("""
**Forklaring:**

| Dekning | Rekker | Tildeles når |
|---|---|---|
| **Single** | ×1 | Klar favoritt eller budsjett brukt |
| **Halvdekk** | ×2 | To utfall nesten like sannsynlige |
| **Heldekkende** | ×3 | Alle tre utfall er reelle |

Optimizer velger kombinasjonen som bruker budsjettet **fullt ut** — alltid.

> **Gjennomsnittlig trygghet**: gjennomsnittlig sannsynlighet for det sterkeste enkeltutfallet
> i alle kamper. Dette er *ikke* sannsynligheten for at hele kupongen vinner.
    """)
