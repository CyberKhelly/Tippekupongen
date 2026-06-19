"""
Results — manually enter match scores for a saved coupon.

Select week / year / coupon type, enter scores, save.
The coupon must have been saved via the main page first.
"""
import streamlit as st
from db.schema import init_db
from db.coupon import list_coupons
from db.history import get_predictions, save_result, get_result, has_predictions

st.set_page_config(
    page_title="Resultater — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] { background-color: #0b1623 !important; border-bottom: 1px solid rgba(255,255,255,0.04) !important; }
.block-container { max-width: 900px !important; padding-top: 2.5rem !important; }
.page-title { font-size: 1.4rem; font-weight: 900; color: #fff; margin-bottom: 0.2rem; }
.page-title .q { color: #f5c518; }
.page-subtitle { font-size: 0.75rem; color: #3a5a78; margin-bottom: 1.5rem; }
.section-head {
    font-size: 0.65rem; font-weight: 700; color: #2e4a64;
    text-transform: uppercase; letter-spacing: 1.8px;
    margin-bottom: 0.5rem; margin-top: 1.2rem;
    border-bottom: 1px solid rgba(255,255,255,0.05); padding-bottom: 0.3rem;
}
.match-label { font-size: 13px; font-weight: 600; color: #c8ddf0; }
.match-meta  { font-size: 10px; color: #3a5a78; }
.result-badge {
    display:inline-block; font-size:11px; font-weight:700; padding:3px 10px;
    border-radius:4px;
}
.rb-h { background:#0c2a14; color:#3aaa78; }
.rb-u { background:#261c04; color:#c8960e; }
.rb-b { background:#0c1e34; color:#5096cc; }
.rb-none { background:rgba(255,255,255,0.04); color:#3a5a78; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Resultater</div>
<div class="page-subtitle">Fyll inn kampresultater for en lagret kupong.</div>
""", unsafe_allow_html=True)

# ── Coupon selector ───────────────────────────────────────────────────────────────

init_db()
all_coupons = list_coupons()  # all weeks

# Filter to only coupons with saved predictions
with_preds = [c for c in all_coupons if has_predictions(c["coupon_id"])]

if not with_preds:
    st.warning("Ingen lagrede kuponger. Gå til hovedsiden og klikk **Lagre kupong** først.")
    st.stop()

col1, col2, col3 = st.columns(3)

with col1:
    weeks = sorted({c["week"] for c in with_preds if c["week"]}, reverse=True)
    sel_week = st.selectbox("Uke", weeks, index=0)
with col2:
    years = sorted({c["year"] for c in with_preds if c["year"]}, reverse=True)
    sel_year = st.selectbox("År", years, index=0)
with col3:
    _key_labels = {"midtuke": "Midtuke", "lordag": "Lørdag", "sondag": "Søndag"}
    coupon_opts = [
        c for c in with_preds
        if c["week"] == sel_week and c["year"] == sel_year
    ]
    if not coupon_opts:
        st.warning(f"Ingen kuponger for uke {sel_week}/{sel_year}.")
        st.stop()
    coupon_labels = {
        c["coupon_id"]: _key_labels.get(
            c["coupon_id"].replace(f"-{sel_week:02d}-{sel_year}", ""), c["coupon_id"]
        )
        for c in coupon_opts
    }
    sel_coupon_id = st.selectbox(
        "Kupongtype",
        options=list(coupon_labels.keys()),
        format_func=lambda x: coupon_labels[x],
    )

st.markdown('<div class="section-head">Kampresultater</div>', unsafe_allow_html=True)

# ── Load predictions ──────────────────────────────────────────────────────────────

preds = get_predictions(sel_coupon_id)

if not preds:
    st.info(
        f"Ingen lagrede prediksjoner for **{coupon_labels.get(sel_coupon_id, sel_coupon_id)}** "
        f"uke {sel_week}/{sel_year}.\n\n"
        "Gå til hovedsiden og klikk **💾 Lagre kupong** først."
    )
    st.stop()

# ── Result entry form ─────────────────────────────────────────────────────────────

with st.form("results_form"):
    score_inputs: dict[str, tuple[int, int]] = {}

    for p in preds:
        fid = p["fixture_id"]
        existing = get_result(fid)
        home_default = existing["home_score"] if existing else 0
        away_default = existing["away_score"] if existing else 0

        c_num, c_home, c_vs, c_away, c_result = st.columns([0.5, 4, 0.5, 4, 2])
        with c_num:
            st.markdown(f"<div style='padding-top:28px;color:#3a5a78;font-size:11px'>{p['match_number']}</div>",
                        unsafe_allow_html=True)
        with c_home:
            home_score = st.number_input(
                p["home_display"],
                min_value=0, max_value=30, value=home_default, step=1,
                key=f"h_{fid}",
            )
        with c_vs:
            st.markdown("<div style='padding-top:28px;text-align:center;color:#3a5a78'>–</div>",
                        unsafe_allow_html=True)
        with c_away:
            away_score = st.number_input(
                p["away_display"],
                min_value=0, max_value=30, value=away_default, step=1,
                key=f"a_{fid}",
            )
        with c_result:
            if existing or home_score != 0 or away_score != 0:
                if home_score > away_score:
                    badge = '<span class="result-badge rb-h">H</span>'
                elif home_score < away_score:
                    badge = '<span class="result-badge rb-b">B</span>'
                else:
                    badge = '<span class="result-badge rb-u">U</span>'
            else:
                badge = '<span class="result-badge rb-none">—</span>'
            st.markdown(f"<div style='padding-top:26px'>{badge}</div>", unsafe_allow_html=True)

        score_inputs[fid] = (home_score, away_score)

    st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
    submitted = st.form_submit_button("Lagre resultater", use_container_width=True, type="primary")

# ── Save results ──────────────────────────────────────────────────────────────────

if submitted:
    saved_count = 0
    for fid, (hs, as_) in score_inputs.items():
        if hs != 0 or as_ != 0:
            save_result(fid, hs, as_, source="manual")
            saved_count += 1

    if saved_count:
        st.success(
            f"{saved_count} av {len(preds)} resultater lagret. "
            "Kjør `python sync.py --evaluate` for å beregne treffprosent."
        )
        st.cache_data.clear()
    else:
        st.warning("Ingen resultater lagret — skriv inn minst ett mål for å lagre.")
