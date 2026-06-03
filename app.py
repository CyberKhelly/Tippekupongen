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
    layout="wide",
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
BUDGET_ROWS   = {32: 32, 96: 96, 192: 192, 384: 384}

# ── Session state defaults ─────────────────────────────────────────────────────
if "coupon_key" not in st.session_state:
    st.session_state.coupon_key = COUPON_KEYS[0]
if "budget" not in st.session_state:
    st.session_state.budget = 192

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
/* Outer main split: generous gap */
[data-testid="stHorizontalBlock"] {
    gap: 2rem !important;
    align-items: flex-start !important;
}
/* Inner button rows (inside a column): tight gap */
[data-testid="column"] [data-testid="stHorizontalBlock"] {
    gap: 6px !important;
}

/* ── App wordmark ───────────────────────────────────────────────── */
.app-wordmark {
    font-size: 1.55rem;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: -0.5px;
    line-height: 1;
}
.app-wordmark .q { color: #f5c518; }

.app-meta-date {
    font-size: 0.78rem;
    color: #5a7a96;
    font-weight: 500;
    white-space: nowrap;
}
.app-subtitle {
    font-size: 0.67rem;
    color: #2e4a64;
    margin-top: 3px;
}

/* ── Header row ─────────────────────────────────────────────────── */
.app-header-row {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
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
    gap: 6px;
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
button[kind="primary"] {
    background-color: #f5c518 !important;
    color: #0b1623 !important;
    border: 2px solid #f5c518 !important;
    font-weight: 700 !important;
    transition: background 0.12s, box-shadow 0.12s !important;
}
button[kind="primary"]:hover {
    background-color: #f7d045 !important;
    border-color: #f7d045 !important;
    box-shadow: 0 0 14px rgba(245,197,24,.28) !important;
}
/* ── Buttons: unselected = ghost ─────────────────────────────────── */
button[kind="secondary"] {
    background-color: rgba(255,255,255,0.04) !important;
    color: rgba(180,206,228,0.5) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
}
button[kind="secondary"]:hover {
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
    font-size: 0.6rem;
    font-weight: 700;
    color: #2e4a64;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    margin-bottom: 0.5rem;
}
.footnote {
    font-size: 0.62rem;
    color: #2e4a64;
    margin-top: 0.85rem;
    line-height: 1.6;
    padding-top: 0.7rem;
    border-top: 1px solid rgba(255,255,255,0.04);
}
.footnote strong { color: #3d6080; }

/* ── Misc ────────────────────────────────────────────────────────── */
hr { border-color: rgba(255,255,255,0.05) !important; margin: 0.75rem 0 !important; }
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

    # Each row: 6px top-pad + 12px name (line-height 1.3) + 1px gap + 9px note (line-height 1.3) + 6px bot-pad ≈ 40px
    row_h = 40
    height = 46 + 24 + len(matches) * row_h + 44
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

    # Build exactly 8 <th> cells — alignment appended per column, never via .replace()
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
        f'</tr>'
    )

    rows_html = ""
    for i, m in enumerate(matches):
        n        = len(picks[m.number])
        cov_lbl  = _cov[n]
        conf_val = round(m.confidence * 100, 1)
        cbg, cfg = conf_colors(conf_val)
        vbg, vfg = _cov_colors[cov_lbl]
        row_bg   = "rgba(255,255,255,0.02)" if i % 2 == 0 else "transparent"

        # Build exactly 8 <td> cells per row — one f-string per cell, no multi-line splits.
        rows_html += (
            f'<tr style="background:{row_bg};">'
            f'<td style="{_td_base}color:#2e4a64;text-align:center;">{m.number}</td>'
            f'<td style="{_td_base}color:#c8ddf0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:160px;">{m.label}</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_h*100,1)}%</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_u*100,1)}%</td>'
            f'<td style="{_td_base}color:#6a90b0;text-align:right;">{round(m.prob_b*100,1)}%</td>'
            f'<td style="{_td_base}text-align:center;font-weight:800;color:#f5c518;">{m.recommendation}</td>'
            f'<td style="{_td_base}text-align:center;"><span style="{_badge}background:{cbg};color:{cfg};">{conf_val:.1f}%</span></td>'
            f'<td style="{_td_base}text-align:center;"><span style="{_badge}background:{vbg};color:{vfg};">{cov_lbl}</span></td>'
            f'</tr>'
        )

    html = (
        '<div style="overflow-x:auto;border-radius:8px;border:1px solid rgba(255,255,255,0.05);">'
        '<table style="width:100%;border-collapse:collapse;'
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
st.markdown("""
<div class="app-header-row">
  <div>
    <div class="app-wordmark">Tippe<span class="q">Q</span>pongen</div>
    <div class="app-subtitle">Basert på estimerte odds · oppdateres ukentlig</div>
  </div>
  <div class="app-meta-date">Uke 23 · 2026</div>
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

    budget = st.session_state.budget

    # Compute
    matches = load_matches(coupon_key)
    picks, total_rows = optimize_coupon(matches, float(budget))

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

    st.markdown(f"""
<div class="summary-strip">
  <div class="s-cell"><div class="s-val">{n_full}</div><div class="s-key">Heldekkende</div></div>
  <div class="s-cell"><div class="s-val">{n_half}</div><div class="s-key">Halvdekk</div></div>
  <div class="s-cell"><div class="s-val">{n_single}</div><div class="s-key">Single</div></div>
  <div class="s-cell"><div class="s-val">{total_rows}</div><div class="s-key">Rekker</div></div>
  <div class="s-cell"><div class="s-val">{total_cost:.0f} NOK</div><div class="s-key">Kostnad</div></div>
  <div class="s-cell"><div class="s-val {rem_cls}">{rem_str} NOK</div><div class="s-key">Rest</div></div>
</div>
""", unsafe_allow_html=True)

# ╔══════════════════════════════════════════════════════╗
# ║  RIGHT PANEL — analysis table (always visible)       ║
# ╚══════════════════════════════════════════════════════╝
with right_col:
    st.markdown('<div class="panel-title">Se kampanalyse</div>', unsafe_allow_html=True)
    render_analysis_table(matches, picks)
    st.markdown("""
<div class="footnote">
<strong>Dekning:</strong> Single ×1 · Halvdekk ×2 · Heldekkende ×3 —
optimizer velger kombinasjonen som bruker budsjettet <em>fullt ut</em>.<br>
<strong>Gjennomsnittlig trygghet:</strong> gjennomsnittlig sannsynlighet for det sterkeste
enkeltutfallet — <em>ikke</em> sannsynligheten for at hele kupongen vinner.
</div>
""", unsafe_allow_html=True)
