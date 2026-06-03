import streamlit as st
import pandas as pd

from models.match import Match
from analysis.probability import process_match
from analysis.classifier import classify_match, classification_label
from analysis.optimizer import optimize_coupon

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Tippekupongen Analyser",
    page_icon="⚽",
    layout="wide",
)

NUM_MATCHES = 12

# ── Classification styling ─────────────────────────────────────────────────────
_CLS_STYLE: dict[str, str] = {
    "Banker":     "color:#155724; background-color:#d4edda; font-weight:bold",
    "Standard":   "color:#0c5460; background-color:#d1ecf1",
    "Half Cover": "color:#856404; background-color:#fff3cd",
    "Full Cover": "color:#721c24; background-color:#f8d7da",
    "Uncertain":  "color:#4a235a; background-color:#e8d5f5",
}

_COVER_STYLE: dict[int, str] = {
    1: "",
    2: "color:#856404; background-color:#fff3cd",
    3: "color:#721c24; background-color:#f8d7da",
}


# ── Helpers ────────────────────────────────────────────────────────────────────
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
            "#":           m.number,
            "Match":       m.label,
            "H %":         round(m.prob_h * 100, 1),
            "U %":         round(m.prob_u * 100, 1),
            "B %":         round(m.prob_b * 100, 1),
            "Pick":        m.recommendation,
            "Confidence":  round(m.confidence * 100, 1),
            "Type":        classification_label(m.classification),
        }
        for m in matches
    ])


def coupon_dataframe(matches: list[Match], picks: dict) -> pd.DataFrame:
    _coverage = {1: "Single", 2: "Half cover", 3: "Full cover"}
    return pd.DataFrame([
        {
            "#":         m.number,
            "Match":     m.label,
            "Picks":     " / ".join(picks[m.number]),
            "Coverage":  _coverage[len(picks[m.number])]
                         + (" ★" if m.classification == "banker" else ""),
            "_n":        len(picks[m.number]),
        }
        for m in matches
    ])


# ── Style functions ────────────────────────────────────────────────────────────
def _style_type(val: str) -> str:
    return _CLS_STYLE.get(val, "")


def _style_confidence(val: float) -> str:
    if val >= 60:
        return "color:#155724; font-weight:bold"
    if val < 45:
        return "color:#721c24"
    return ""


def _style_coverage(col: pd.Series) -> list[str]:
    return [_COVER_STYLE.get(row, "") for row in col]


# ── Page header ────────────────────────────────────────────────────────────────
st.title("⚽ Tippekupongen Analyser")
st.caption(
    "Enter bookmaker odds for all 12 matches, then click **Analyse Coupon** "
    "to get probability-based recommendations and an optimized coupon."
)

# ── Input form ─────────────────────────────────────────────────────────────────
with st.form("coupon_form"):

    # Column headers
    hdr = st.columns([0.35, 2.4, 2.4, 0.9, 0.9, 0.9])
    for col, label in zip(hdr, ["#", "Home team", "Away team", "H odds", "U odds", "B odds"]):
        col.markdown(f"**{label}**")

    raw_inputs: list[tuple] = []
    for i in range(1, NUM_MATCHES + 1):
        c = st.columns([0.35, 2.4, 2.4, 0.9, 0.9, 0.9])
        c[0].markdown(f"**{i}**")
        home = c[1].text_input("h", placeholder=f"Home {i}",  key=f"home_{i}", label_visibility="collapsed")
        away = c[2].text_input("a", placeholder=f"Away {i}",  key=f"away_{i}", label_visibility="collapsed")
        oh   = c[3].number_input("H", min_value=1.01, max_value=100.0, value=2.00, step=0.05, format="%.2f", key=f"oh_{i}", label_visibility="collapsed")
        ou   = c[4].number_input("U", min_value=1.01, max_value=100.0, value=3.40, step=0.05, format="%.2f", key=f"ou_{i}", label_visibility="collapsed")
        ob   = c[5].number_input("B", min_value=1.01, max_value=100.0, value=3.60, step=0.05, format="%.2f", key=f"ob_{i}", label_visibility="collapsed")
        raw_inputs.append((i, home, away, oh, ou, ob))

    st.divider()

    bc = st.columns([1, 1, 4])
    budget      = bc[0].number_input("Budget (NOK)",        min_value=1.0,  value=192.0, step=8.0)
    cost_per_row = bc[1].number_input("Cost per row (NOK)", min_value=0.10, value=1.0,   step=0.10)
    submitted   = st.form_submit_button("Analyse Coupon", type="primary")

# ── Results ────────────────────────────────────────────────────────────────────
if submitted:
    matches = build_matches(raw_inputs)
    picks, total_rows = optimize_coupon(matches, budget, cost_per_row)

    bankers   = [m for m in matches if m.classification == "banker"]
    covers    = [m for m in matches if m.classification in ("uncertain", "full_cover", "half_cover")]
    avg_conf  = sum(m.confidence for m in matches) / len(matches)
    total_cost = total_rows * cost_per_row

    # ── Summary metrics ────────────────────────────────────────────────────────
    st.divider()
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Bankers",          len(bankers))
    col2.metric("Cover candidates", len(covers))
    col3.metric("Avg confidence",   f"{avg_conf * 100:.1f}%")
    col4.metric("Coupon rows",      total_rows)
    col5.metric("Total cost",       f"{total_cost:.2f} NOK")

    # ── Match analysis ─────────────────────────────────────────────────────────
    st.subheader("Match Analysis")

    df_analysis = analysis_dataframe(matches)
    styled_analysis = (
        df_analysis.style
        .map(_style_type,       subset=["Type"])
        .map(_style_confidence, subset=["Confidence"])
        .format({"H %": "{:.1f}%", "U %": "{:.1f}%", "B %": "{:.1f}%", "Confidence": "{:.1f}%"})
        .set_properties(subset=["Pick"], **{"font-weight": "bold"})
    )
    st.dataframe(styled_analysis, use_container_width=True, hide_index=True)

    # ── Coupon ─────────────────────────────────────────────────────────────────
    st.subheader("Optimized Coupon")

    df_coupon = coupon_dataframe(matches, picks)
    styled_coupon = (
        df_coupon.drop(columns=["_n"])
        .style
        .apply(_style_coverage, subset=["Coverage"])
    )
    st.dataframe(styled_coupon, use_container_width=True, hide_index=True)

    remaining = budget - total_cost
    if remaining >= 0:
        st.success(f"Budget used: {total_cost:.2f} NOK — {remaining:.2f} NOK remaining.")
    else:
        st.error(f"Over budget by {abs(remaining):.2f} NOK.")

    # ── Classification legend ──────────────────────────────────────────────────
    with st.expander("Classification guide"):
        st.markdown("""
| Type | Meaning |
|------|---------|
| **Banker** | Confidence ≥ 60% — strong single pick |
| **Standard** | One outcome leads, but below banker threshold |
| **Half Cover** | Top two outcomes within 13 pp — consider covering both |
| **Full Cover** | All three outcomes within 10 pp — very open match |
| **Uncertain** | No outcome reaches 45% — maximum uncertainty |
        """)
