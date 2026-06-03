import re
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd

from models.match import Match
from analysis.probability import process_match
from analysis.classifier import classify_match, classification_label
from analysis.optimizer import optimize_coupon
from data.coupon_week23_2026 import COUPONS

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tippekupongen Analyser",
    page_icon="⚽",
    layout="wide",
)

NUM_MATCHES = 12

# Coupon options for the dropdown — built from the data file
_COUPON_OPTIONS = {v["label"]: k for k, v in COUPONS.items()}

EXAMPLE_FIXTURES = [
    ("Arsenal",     "Chelsea",      1.85, 3.60, 4.20),
    ("Man City",    "Liverpool",    2.10, 3.40, 3.50),
    ("Rosenborg",   "Molde",        1.50, 4.00, 6.00),
    ("Brann",       "Viking",       2.60, 3.10, 2.80),
    ("Odd",         "Sarpsborg",    2.20, 3.20, 3.30),
    ("Real Madrid", "Barcelona",    2.00, 3.50, 3.80),
    ("Juventus",    "Inter Milan",  2.30, 3.20, 3.10),
    ("Dortmund",    "Bayern",       3.80, 3.50, 1.95),
    ("Ajax",        "PSV",          2.00, 3.40, 3.70),
    ("Feyenoord",   "AZ Alkmaar",   2.10, 3.20, 3.50),
    ("Celtic",      "Rangers",      2.40, 3.30, 2.90),
    ("Bodo/Glimt",  "Lillestrom",   1.40, 4.50, 8.00),
]

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* ── Coupon card ── */
.nt-coupon {
    max-width: 700px;
    margin: 0 auto 1.5rem auto;
    font-family: 'Segoe UI', Arial, sans-serif;
    border: 3px solid #003087;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 6px 20px rgba(0,48,135,0.18);
}
.nt-header {
    background: linear-gradient(135deg, #002060 0%, #0052cc 100%);
    color: #fff;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.nt-header-left {}
.nt-title {
    font-size: 22px;
    font-weight: 900;
    letter-spacing: 4px;
    line-height: 1;
}
.nt-sub {
    font-size: 11px;
    opacity: 0.7;
    margin-top: 3px;
    letter-spacing: 1px;
}
.nt-logo { font-size: 34px; }
.nt-col-hdr {
    display: grid;
    grid-template-columns: 28px 1fr 72px 38px 38px 38px;
    gap: 4px;
    padding: 7px 16px;
    background: #dce8f8;
    border-bottom: 2px solid #003087;
    font-size: 11px;
    font-weight: 800;
    color: #003087;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.nt-col-hdr span { text-align: center; }
.nt-col-hdr span.nt-match-col { text-align: left; }
.nt-row {
    display: grid;
    grid-template-columns: 28px 1fr 72px 38px 38px 38px;
    gap: 4px;
    padding: 6px 16px;
    border-bottom: 1px solid #e2ecf8;
    align-items: center;
}
.nt-row:last-of-type { border-bottom: none; }
.nt-row:nth-child(even) { background: #f4f8ff; }
.nt-row:nth-child(odd)  { background: #ffffff; }
.nt-row.nt-banker       { background: #fffde7 !important; }
.nt-num {
    font-size: 12px;
    color: #888;
    font-weight: 700;
    text-align: center;
}
.nt-match {
    font-size: 13px;
    color: #1a1a2e;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 4px;
}
/* Confidence pill */
.nt-conf {
    position: relative;
    height: 20px;
    background: #e5e5e5;
    border-radius: 10px;
    overflow: hidden;
    display: flex;
    align-items: center;
}
.nt-conf-fill {
    position: absolute;
    left: 0; top: 0; bottom: 0;
    border-radius: 10px;
}
.nt-conf-label {
    position: relative;
    z-index: 1;
    font-size: 10px;
    font-weight: 800;
    color: #fff;
    padding-left: 7px;
    text-shadow: 0 1px 2px rgba(0,0,0,0.45);
    white-space: nowrap;
}
/* Pick circles */
.nt-pick {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    border: 2px solid #ccc;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 800;
    color: #bbb;
    margin: 0 auto;
    background: #f7f7f7;
}
.nt-pick.sel {
    background: #003087;
    color: #fff;
    border-color: #003087;
    box-shadow: 0 2px 8px rgba(0,48,135,0.35);
}
.nt-pick.sel-multi {
    background: #c0392b;
    color: #fff;
    border-color: #c0392b;
    box-shadow: 0 2px 8px rgba(192,57,43,0.35);
}
/* Footer */
.nt-footer {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 0;
    background: #dce8f8;
    border-top: 2px solid #003087;
    font-size: 13px;
    font-weight: 700;
    color: #002060;
}
.nt-footer-cell {
    padding: 10px 16px;
    text-align: center;
    border-right: 1px solid #c5d8f0;
}
.nt-footer-cell:last-child { border-right: none; }
.nt-footer-label {
    font-size: 10px;
    font-weight: 600;
    color: #5577aa;
    text-transform: uppercase;
    letter-spacing: 1px;
}
.nt-footer-val {
    font-size: 16px;
    font-weight: 900;
    color: #002060;
}

/* ── Mobile ── */
@media screen and (max-width: 680px) {
    .nt-title { font-size: 17px; letter-spacing: 2px; }
    .nt-logo  { font-size: 26px; }
    .nt-col-hdr, .nt-row {
        grid-template-columns: 22px 1fr 56px 30px 30px 30px;
        padding: 5px 8px;
        gap: 2px;
    }
    .nt-match { font-size: 11px; }
    .nt-pick  { width: 26px; height: 26px; font-size: 10px; }
    .nt-conf  { height: 16px; }
    .nt-conf-label { font-size: 9px; }
}

/* ── Streamlit tweaks ── */
div[data-testid="stForm"] { border: none; padding: 0; }
</style>
""", unsafe_allow_html=True)

# ── Classification and confidence styling ──────────────────────────────────────
_CLS_STYLE = {
    "Banker":     "color:#155724; background-color:#d4edda; font-weight:bold",
    "Standard":   "color:#0c5460; background-color:#d1ecf1",
    "Half Cover": "color:#856404; background-color:#fff3cd",
    "Full Cover": "color:#721c24; background-color:#f8d7da",
    "Uncertain":  "color:#4a235a; background-color:#e8d5f5",
}

# Confidence fill color for the HTML coupon bar
def _conf_color(pct: float) -> str:
    if pct >= 60:
        return "#28a745"
    if pct >= 52:
        return "#85c740"
    if pct >= 45:
        return "#ffc107"
    return "#dc3545"

# Confidence cell style for the analysis dataframe
def _style_confidence(val: float) -> str:
    if val >= 60:
        return "background-color:#d4edda; color:#155724; font-weight:bold"
    if val >= 52:
        return "background-color:#e8f5d0; color:#3a6b1a"
    if val >= 45:
        return "background-color:#fff3cd; color:#856404"
    return "background-color:#f8d7da; color:#721c24"

def _style_type(val: str) -> str:
    return _CLS_STYLE.get(val, "")


# ── Session state ──────────────────────────────────────────────────────────────
if "analysis" not in st.session_state:
    st.session_state.analysis = None


# ── Parse fixtures ─────────────────────────────────────────────────────────────
def parse_fixtures(text: str) -> list[tuple[str, str]]:
    fixtures = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Strip leading "1 ", "1. ", "1) " etc.
        line = re.sub(r"^\d+[\.\)\s]\s*", "", line).strip()
        # Try separators in order of preference
        for sep in (" - ", " – ", "-"):
            if sep in line:
                parts = line.split(sep, 1)
                home, away = parts[0].strip(), parts[1].strip()
                if home and away:
                    fixtures.append((home, away))
                    break
    return fixtures


# ── Callbacks ──────────────────────────────────────────────────────────────────
def _apply_matches(matches: list[tuple]) -> None:
    """Write a list of (home, away, oh, ou, ob) tuples into session state."""
    for i, (home, away, oh, ou, ob) in enumerate(matches, 1):
        st.session_state[f"home_{i}"] = home
        st.session_state[f"away_{i}"] = away
        st.session_state[f"oh_{i}"]   = float(oh)
        st.session_state[f"ou_{i}"]   = float(ou)
        st.session_state[f"ob_{i}"]   = float(ob)
    st.session_state.analysis = None


def cb_load_this_week():
    label = st.session_state.get("coupon_selector", list(_COUPON_OPTIONS.keys())[0])
    key   = _COUPON_OPTIONS[label]
    _apply_matches(COUPONS[key]["matches"])


def cb_load_example():
    _apply_matches(EXAMPLE_FIXTURES)


def cb_parse_fixtures():
    text = st.session_state.get("paste_input", "")
    fixtures = parse_fixtures(text)
    if not fixtures:
        st.session_state["_parse_error"] = "No valid fixtures found. Check the format."
        return
    padded = [(h, a, 2.00, 3.40, 3.60) for h, a in fixtures[:NUM_MATCHES]]
    _apply_matches(padded)
    st.session_state["_parse_error"] = None


# ── Data helpers ───────────────────────────────────────────────────────────────
def build_matches(raw: list[tuple]) -> list[Match]:
    matches = []
    for i, home, away, oh, ou, ob in raw:
        home = home.strip() or f"Home {i}"
        away = away.strip() or f"Away {i}"
        m = Match(number=i, home_team=home, away_team=away,
                  odds_h=oh, odds_u=ou, odds_b=ob)
        process_match(m)
        classify_match(m)
        matches.append(m)
    return matches


def analysis_dataframe(matches: list[Match]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "#":          m.number,
            "Match":      m.label,
            "H %":        round(m.prob_h * 100, 1),
            "U %":        round(m.prob_u * 100, 1),
            "B %":        round(m.prob_b * 100, 1),
            "Pick":       m.recommendation,
            "Confidence": round(m.confidence * 100, 1),
            "Type":       classification_label(m.classification),
        }
        for m in matches
    ])


# ── Optimizer decision table ───────────────────────────────────────────────────
def render_decision_table(matches: list[Match], picks: dict) -> None:
    """Transparency table: shows WHY each match got its coverage level."""
    _label = {1: "Single", 2: "Half Cover", 3: "Full Cover"}

    rows = []
    for m in matches:
        n          = len(picks[m.number])
        picks_str  = " / ".join(picks[m.number])
        rows.append({
            "#":        m.number,
            "Match":    m.label,
            "Conf":     round(m.confidence * 100, 1),
            "Coverage": _label[n],
            "Picks":    picks_str,
        })

    df = pd.DataFrame(rows)

    def _style_cov(val: str) -> str:
        return {
            "Full Cover": "background-color:#f8d7da; color:#721c24; font-weight:bold",
            "Half Cover": "background-color:#fff3cd; color:#856404; font-weight:bold",
            "Single":     "background-color:#d1ecf1; color:#0c5460",
        }.get(val, "")

    styled = (
        df.style
        .map(_style_cov,        subset=["Coverage"])
        .map(_style_confidence, subset=["Conf"])
        .format({"Conf": "{:.1f}%"})
        .set_properties(subset=["Picks"], **{"font-weight": "bold"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ── Coupon card (rendered via components.v1.html to avoid markdown stripping) ──
def render_coupon_card(
    matches: list[Match],
    picks: dict,
    total_rows: int,
    budget: float,
    cost_per_row: float,
) -> None:
    total_cost = total_rows * cost_per_row
    remaining  = budget - total_cost
    rem_color  = "#28a745" if remaining >= 0 else "#dc3545"

    def circle(label: str, selected: bool, multi: bool) -> str:
        if selected:
            bg, fg, bd = ("#003087", "#fff", "#003087") if not multi else ("#c0392b", "#fff", "#c0392b")
        else:
            bg, fg, bd = ("#f0f2f6", "#aaa", "#ccc")
        return (
            f'<div style="width:36px;height:36px;border-radius:50%;'
            f'background:{bg};color:{fg};border:2px solid {bd};'
            f'display:flex;align-items:center;justify-content:center;'
            f'font-size:12px;font-weight:800;">{label}</div>'
        )

    _cov_color = {1: "#0c5460", 2: "#856404", 3: "#721c24"}
    _cov_label = {1: "Single", 2: "Half Cover", 3: "Full Cover"}

    match_rows = ""
    for idx, m in enumerate(matches):
        mp    = picks[m.number]
        n     = len(mp)
        multi = n > 1
        bg    = "#f8fafe" if idx % 2 == 0 else "#ffffff"

        match_rows += (
            f'<div style="display:grid;grid-template-columns:28px 1fr auto;gap:8px;'
            f'padding:8px 16px;background:{bg};border-bottom:1px solid #e2ecf8;align-items:center;">'
            f'  <span style="color:#999;font-size:11px;font-weight:700;text-align:center;">{m.number}</span>'
            f'  <div>'
            f'    <div style="font-size:13px;font-weight:600;color:#1a1a2e;">{m.label}</div>'
            f'    <div style="font-size:10px;font-weight:700;color:{_cov_color[n]};margin-top:1px;">'
            f'      {_cov_label[n]}'
            f'    </div>'
            f'  </div>'
            f'  <div style="display:flex;gap:5px;">'
            f'    {circle("H","H" in mp, multi)}'
            f'    {circle("U","U" in mp, multi)}'
            f'    {circle("B","B" in mp, multi)}'
            f'  </div>'
            f'</div>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0;box-sizing:border-box;}}</style>
</head><body style="font-family:'Segoe UI',Arial,sans-serif;background:transparent;">
<div style="border:3px solid #003087;border-radius:12px;overflow:hidden;
            box-shadow:0 4px 16px rgba(0,48,135,.15);">
  <div style="background:linear-gradient(135deg,#002060,#0052cc);
              color:#fff;padding:14px 20px;
              display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-size:20px;font-weight:900;letter-spacing:4px;">TIPPEKUPONGEN</div>
      <div style="font-size:11px;opacity:.7;margin-top:2px;">Norsk Tipping &middot; Analyseresultat</div>
    </div>
    <div style="font-size:30px;">&#9917;</div>
  </div>
  <div style="display:grid;grid-template-columns:28px 1fr auto;gap:8px;
              padding:6px 16px;background:#dce8f8;
              border-bottom:2px solid #003087;
              font-size:10px;font-weight:800;color:#003087;
              text-transform:uppercase;letter-spacing:1px;">
    <span style="text-align:center;">#</span>
    <span>Kamp</span>
    <div style="display:flex;gap:5px;">
      <span style="width:36px;text-align:center;">H</span>
      <span style="width:36px;text-align:center;">U</span>
      <span style="width:36px;text-align:center;">B</span>
    </div>
  </div>
  <div>{match_rows}</div>
  <div style="display:grid;grid-template-columns:repeat(3,1fr);
              background:#dce8f8;border-top:2px solid #003087;">
    <div style="padding:10px 16px;text-align:center;border-right:1px solid #c5d8f0;">
      <div style="font-size:10px;font-weight:600;color:#5577aa;text-transform:uppercase;letter-spacing:1px;">Rekker</div>
      <div style="font-size:20px;font-weight:900;color:#002060;">{total_rows}</div>
    </div>
    <div style="padding:10px 16px;text-align:center;border-right:1px solid #c5d8f0;">
      <div style="font-size:10px;font-weight:600;color:#5577aa;text-transform:uppercase;letter-spacing:1px;">Kostnad</div>
      <div style="font-size:20px;font-weight:900;color:#002060;">{total_cost:.2f} NOK</div>
    </div>
    <div style="padding:10px 16px;text-align:center;">
      <div style="font-size:10px;font-weight:600;color:#5577aa;text-transform:uppercase;letter-spacing:1px;">Gjenstår</div>
      <div style="font-size:20px;font-weight:900;color:{rem_color};">{remaining:+.2f} NOK</div>
    </div>
  </div>
</div>
</body></html>"""

    card_height = 60 + 35 + len(matches) * 56 + 58
    components.html(html, height=card_height, scrolling=False)


# ══════════════════════════════════════════════════════════════════════════════
# Page layout
# ══════════════════════════════════════════════════════════════════════════════

st.title("⚽ Tippekupongen Analyser")
st.caption(
    "Enter odds for all 12 matches and get probability-based recommendations "
    "and an optimized coupon within your budget."
)

# ── Load / Paste fixtures ──────────────────────────────────────────────────────
has_teams = any(st.session_state.get(f"home_{i}") for i in range(1, NUM_MATCHES + 1))
with st.expander("Load or Paste Fixtures", expanded=not has_teams):

    # ── This week's real coupon ────────────────────────────────────────────────
    st.markdown("**Denne uken (uke 23, 2026)** — velg kupong og trykk Last inn:")
    sel_col, btn_col = st.columns([3, 1])
    sel_col.selectbox(
        "Kupong",
        options=list(_COUPON_OPTIONS.keys()),
        key="coupon_selector",
        label_visibility="collapsed",
    )
    btn_col.button(
        "Last inn",
        on_click=cb_load_this_week,
        type="primary",
        use_container_width=True,
    )
    st.caption(
        "Kamper og odds hentes fra data/coupon_week23_2026.py. "
        "Odds er estimert — rediger filen for å bruke live-odds fra bookmaker."
    )

    st.divider()

    st.button(
        "Load Example Coupon",
        on_click=cb_load_example,
        help="Fill all 12 matches with generic example fixtures for testing.",
    )
    st.markdown("**Or paste your own fixtures:**")
    st.text_area(
        "Fixtures",
        key="paste_input",
        height=160,
        placeholder=(
            "1 Tyskland - Norge\n"
            "2 Østerrike - Slovenia\n"
            "3 Polen - Frankrike\n"
            "..."
        ),
        label_visibility="collapsed",
    )
    st.button("Parse Fixtures", on_click=cb_parse_fixtures, type="primary")

    err = st.session_state.get("_parse_error")
    if err:
        st.error(err)

st.divider()

# ── Seed odds defaults into session state on first load ────────────────────────
# Avoids Streamlit warning when _apply_matches sets state AND value= is also set.
for _i in range(1, NUM_MATCHES + 1):
    st.session_state.setdefault(f"oh_{_i}", 2.00)
    st.session_state.setdefault(f"ou_{_i}", 3.40)
    st.session_state.setdefault(f"ob_{_i}", 3.60)

# ── Match input form ───────────────────────────────────────────────────────────
with st.form("coupon_form"):

    # Header row
    hdr = st.columns([0.3, 2.5, 2.5, 0.85, 0.85, 0.85])
    for col, label in zip(hdr, ["#", "Home team", "Away team", "H", "U", "B"]):
        col.markdown(f"**{label}**")

    raw_inputs: list[tuple] = []
    for i in range(1, NUM_MATCHES + 1):
        c = st.columns([0.3, 2.5, 2.5, 0.85, 0.85, 0.85])
        c[0].markdown(f"**{i}**")
        home = c[1].text_input(
            "home", placeholder=f"Home {i}",
            key=f"home_{i}", label_visibility="collapsed",
        )
        away = c[2].text_input(
            "away", placeholder=f"Away {i}",
            key=f"away_{i}", label_visibility="collapsed",
        )
        oh = c[3].number_input(
            "H", min_value=1.01, max_value=100.0,
            step=0.05, format="%.2f",
            key=f"oh_{i}", label_visibility="collapsed",
        )
        ou = c[4].number_input(
            "U", min_value=1.01, max_value=100.0,
            step=0.05, format="%.2f",
            key=f"ou_{i}", label_visibility="collapsed",
        )
        ob = c[5].number_input(
            "B", min_value=1.01, max_value=100.0,
            step=0.05, format="%.2f",
            key=f"ob_{i}", label_visibility="collapsed",
        )
        raw_inputs.append((i, home, away, oh, ou, ob))

    st.divider()

    bc = st.columns([1, 1, 4])
    budget       = bc[0].number_input("Budget (NOK)",        min_value=1.0,  value=192.0, step=8.0)
    cost_per_row = bc[1].number_input("Cost per row (NOK)",  min_value=0.10, value=1.0,   step=0.10)
    submitted    = st.form_submit_button("Analyse Coupon", type="primary")

# ── Run analysis and store in session state ────────────────────────────────────
if submitted:
    matches = build_matches(raw_inputs)
    picks, total_rows = optimize_coupon(matches, budget, cost_per_row)
    st.session_state.analysis = {
        "matches":      matches,
        "picks":        picks,
        "total_rows":   total_rows,
        "budget":       budget,
        "cost_per_row": cost_per_row,
    }

# ── Render results from session state (persists across reruns) ─────────────────
if st.session_state.analysis:
    a             = st.session_state.analysis
    matches       = a["matches"]
    picks         = a["picks"]
    total_rows    = a["total_rows"]
    budget        = a["budget"]
    cost_per_row  = a["cost_per_row"]
    total_cost    = total_rows * cost_per_row

    bankers  = [m for m in matches if m.classification == "banker"]
    covers   = [m for m in matches if m.classification in ("uncertain", "full_cover", "half_cover")]
    avg_conf = sum(m.confidence for m in matches) / len(matches)

    # ── Summary row ───────────────────────────────────────────────────────────
    st.divider()
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Bankers",          len(bankers))
    c2.metric("Cover candidates", len(covers))
    c3.metric("Avg confidence",   f"{avg_conf * 100:.1f}%")
    c4.metric("Coupon rows",      total_rows)
    c5.metric("Total cost",       f"{total_cost:.2f} NOK")

    # ── Match analysis table ──────────────────────────────────────────────────
    st.subheader("Match Analysis")
    df = analysis_dataframe(matches)
    styled = (
        df.style
        .map(_style_type,       subset=["Type"])
        .map(_style_confidence, subset=["Confidence"])
        .format({
            "H %": "{:.1f}%", "U %": "{:.1f}%",
            "B %": "{:.1f}%", "Confidence": "{:.1f}%",
        })
        .set_properties(subset=["Pick"], **{"font-weight": "bold", "text-align": "center"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Optimized coupon ──────────────────────────────────────────────────────
    st.subheader("Optimized Coupon")
    st.caption(
        "Most uncertain matches are upgraded first. "
        "Half Cover = top-2 outcomes by probability. Full Cover = all three."
    )
    render_decision_table(matches, picks)
    render_coupon_card(matches, picks, total_rows, budget, cost_per_row)

    # ── How the optimizer works ───────────────────────────────────────────────
    with st.expander("How the optimizer works"):
        st.markdown("""
**Algorithm — depth-first, uncertainty-first:**

1. All 12 matches start as **single picks** (1 row total).
2. Matches are sorted by confidence ascending — least confident first.
3. For each match the optimizer upgrades it one level at a time:
   - **1 pick → 2 picks (Half Cover):** costs ×2 rows. Picks the top-2 outcomes by probability.
   - **2 picks → 3 picks (Full Cover):** costs ×1.5 rows. Picks all three outcomes.
4. It keeps upgrading the same match until the next upgrade exceeds the budget, then moves to the next most uncertain match.
5. High-confidence matches are processed last and are typically left as singles.

| Coverage | Row cost | Assigned when |
|---|---|---|
| **Single** | ×1 | High confidence or budget exhausted |
| **Half Cover** | ×2 | Medium uncertainty — top-2 picks by probability |
| **Full Cover** | ×3 | Low confidence — all three outcomes covered |
        """)
