import re
import streamlit as st
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


# ── Coupon HTML renderer ───────────────────────────────────────────────────────
def _pick_html(label: str, selected: bool, multi: bool) -> str:
    if not selected:
        return f'<div class="nt-pick">{label}</div>'
    cls = "sel-multi" if multi else "sel"
    return f'<div class="nt-pick {cls}">{label}</div>'


def render_coupon_html(
    matches: list[Match],
    picks: dict,
    total_rows: int,
    budget: float,
    cost_per_row: float,
) -> None:
    total_cost = total_rows * cost_per_row
    remaining  = budget - total_cost

    rows_html = ""
    for m in matches:
        match_picks = picks[m.number]
        multi       = len(match_picks) > 1
        is_banker   = m.classification == "banker"
        conf_pct    = round(m.confidence * 100)
        fill_color  = _conf_color(conf_pct)
        label       = m.label if len(m.label) <= 30 else m.label[:29] + "…"

        banker_badge = (
            ' <span style="background:#f9a825;color:#000;font-size:9px;'
            'padding:1px 5px;border-radius:3px;font-weight:900;'
            'vertical-align:middle;">★ BANKER</span>'
            if is_banker else ""
        )

        h_html = _pick_html("H", "H" in match_picks, multi)
        u_html = _pick_html("U", "U" in match_picks, multi)
        b_html = _pick_html("B", "B" in match_picks, multi)

        row_class = "nt-row nt-banker" if is_banker else "nt-row"

        rows_html += f"""
        <div class="{row_class}">
            <span class="nt-num">{m.number}</span>
            <span class="nt-match">{label}{banker_badge}</span>
            <div class="nt-conf">
                <div class="nt-conf-fill"
                     style="width:{conf_pct}%; background:{fill_color};"></div>
                <span class="nt-conf-label">{conf_pct}%</span>
            </div>
            {h_html}{u_html}{b_html}
        </div>
        """

    html = f"""
    <div class="nt-coupon">
        <div class="nt-header">
            <div class="nt-header-left">
                <div class="nt-title">TIPPEKUPONGEN</div>
                <div class="nt-sub">Norsk Tipping &middot; Analyseresultat</div>
            </div>
            <div class="nt-logo">⚽</div>
        </div>
        <div class="nt-col-hdr">
            <span>#</span>
            <span class="nt-match-col">Kamp</span>
            <span>Conf</span>
            <span>H</span>
            <span>U</span>
            <span>B</span>
        </div>
        {rows_html}
        <div class="nt-footer">
            <div class="nt-footer-cell">
                <div class="nt-footer-label">Rekker</div>
                <div class="nt-footer-val">{total_rows}</div>
            </div>
            <div class="nt-footer-cell">
                <div class="nt-footer-label">Kostnad</div>
                <div class="nt-footer-val">{total_cost:.2f} NOK</div>
            </div>
            <div class="nt-footer-cell">
                <div class="nt-footer-label">Gjenstår</div>
                <div class="nt-footer-val"
                     style="color:{'#28a745' if remaining >= 0 else '#dc3545'}">
                    {remaining:+.2f} NOK
                </div>
            </div>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


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

    # ── Coupon visualization ──────────────────────────────────────────────────
    st.subheader("Optimized Coupon")
    render_coupon_html(matches, picks, total_rows, budget, cost_per_row)

    # ── Classification guide ──────────────────────────────────────────────────
    with st.expander("Classification guide"):
        st.markdown("""
| Type | Trigger | Recommended action |
|---|---|---|
| **Banker** | Confidence ≥ 60% | Single pick — no cover needed |
| **Standard** | One outcome leads clearly | Single pick |
| **Half Cover** | Top two outcomes within 13pp | Cover both top outcomes |
| **Full Cover** | All three within 10pp | Cover all three |
| **Uncertain** | No outcome reaches 45% | Full cover or skip |

**Confidence bar color:** Green ≥ 60% · Yellow-green 52–60% · Yellow 45–52% · Red < 45%
        """)
