"""
History — past coupon performance (Phase 8A).

Six sections:
  1. Evaluerte kuponger    — summary table with strategy / PVR / hit rate
  2. Strategi-ytelse       — aggregate per strategy across all evaluated coupons
  3. CDS-validering        — saved CDS buckets (frozen at save time); no live data
  4. Overbevisning vs nødvendige — conviction singles vs halvdekk/heldekk
  5. Modell vs NT-tips     — model accuracy vs public top-pick accuracy
  6. PVR vs utdeling       — PVR at save time vs actual payout (when available)
  + Kupongdetaljer         — per-coupon pick-level view with CLV

CDS section uses ONLY snapshot data from pick_evaluations. For coupons saved
before Phase 8, cds/nt_correct are NULL and those rows are excluded — they are
never backfilled from live coupon_fixtures.public_h/u/b.
"""
import json
import streamlit as st
from db.schema import init_db
from db.history import (
    list_evaluated_coupons, list_coupons_with_predictions,
    get_results_for_coupon, get_evaluation,
)
from db.evaluation import (
    get_strategy_performance, get_cds_validation,
    get_conviction_stats, get_nt_model_comparison,
    get_pvr_payout_data, get_pick_evaluations,
)
from db.odds_movement import get_clv_for_coupon


def _fmt_nok(value) -> str:
    """Return '192 NOK' for numeric values, '—' for None / missing / non-numeric."""
    try:
        return f"{float(value):.0f} NOK"
    except (TypeError, ValueError):
        return "—"


st.set_page_config(
    page_title="Historikk — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] { background-color: #0b1623 !important; border-bottom: 1px solid rgba(255,255,255,0.04) !important; }
.block-container { max-width: 1180px !important; padding-top: 2.5rem !important; }
.page-title { font-size: 1.4rem; font-weight: 900; color: #fff; margin-bottom: 0.2rem; }
.page-title .q { color: #f5c518; }
.page-subtitle { font-size: 0.75rem; color: #3a5a78; margin-bottom: 1.5rem; }
.section-head {
    font-size: 0.78rem; font-weight: 700; color: #4a8abc;
    text-transform: uppercase; letter-spacing: 1.4px;
    margin-bottom: 0.6rem; margin-top: 1.8rem;
    border-left: 2px solid rgba(245,197,24,0.45);
    padding-left: 0.65rem; padding-bottom: 0.25rem;
}
.hist-table { width:100%; border-collapse:collapse; font-family:'Segoe UI',system-ui,Arial,sans-serif; font-size:11.5px; }
.hist-table th {
    font-size:9px; font-weight:700; color:#5a7a9a; text-transform:uppercase; letter-spacing:1.2px;
    padding:6px 8px; background:rgba(255,255,255,0.04); border-bottom:1px solid rgba(255,255,255,0.07);
    text-align:left; white-space:nowrap;
}
.hist-table td { padding:5px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.03); vertical-align:middle; }
.hist-table tr:nth-child(even) td { background:rgba(255,255,255,0.04); }
.hist-table .dim { color:#3a5a78; }
.badge { display:inline-block; font-size:9px; font-weight:700; padding:2px 7px; border-radius:4px; white-space:nowrap; }
.b-complete  { background:#0c2a14; color:#3aaa78; }
.b-partial   { background:#261c04; color:#c8960e; }
.b-pending   { background:#0c1e34; color:#6d90aa; }
.detail-table { width:100%; border-collapse:collapse; font-family:'Segoe UI',system-ui,Arial,sans-serif; font-size:11px; }
.detail-table th { font-size:9px; font-weight:700; color:#5a7a9a; text-transform:uppercase; letter-spacing:1.1px; padding:6px 8px; background:rgba(255,255,255,0.04); border-bottom:1px solid rgba(255,255,255,0.07); white-space:nowrap; }
.detail-table td { padding:5px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.025); vertical-align:middle; }
.detail-table tr:nth-child(even) td { background:rgba(255,255,255,0.04); }
.tick  { color:#3aaa78; font-size:14px; }
.cross { color:#e74c3c; font-size:14px; }
.pick-covered { color:#3aaa78; font-weight:700; }
.pick-miss    { color:#e74c3c; }
details summary {
    cursor:pointer; color:#3a5a78; font-size:9.5px;
    letter-spacing:0.5px; user-select:none; list-style:none;
    padding:2px 0;
}
details summary::-webkit-details-marker { display:none; }
details[open] summary { color:#8aaec8; }
.ap { padding:5px 2px 2px 2px; display:flex; flex-wrap:wrap; gap:6px 14px; }
.ap-item { font-size:9.5px; }
.ap-lbl { color:#5a7a9a; margin-right:3px; }
.ap-val { color:#8aaec8; }
.ap-val.pos { color:#3aaa78; }
.ap-val.neg { color:#e74c3c; }
.glossary { background:rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05);
    border-radius:4px; padding:12px 16px; margin-bottom:1rem; }
.glossary dt { font-size:10px; font-weight:700; color:#8aaec8; margin-top:6px; }
.glossary dd { font-size:10px; color:#607888; margin:0 0 0 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Historikk</div>
<div class="page-subtitle">Evaluering av lagrede kuponger. Alle analyse-verdier er fryst ved lagringstidspunkt.</div>
""", unsafe_allow_html=True)

init_db()

with st.expander("Ordliste — begrepsforklaringer"):
    st.markdown("""
<div class="glossary"><dl>
<dt>CDS — Crowd Disagreement Score (Folkeavvik)</dt>
<dd>Prosentpoengs differanse mellom modellens topptips-sannsynlighet og NT-folkets prosent for samme utfall. Høy CDS = stor uenighet mellom modell og folkemening. Lagret ved kupongtidspunkt.</dd>
<dt>VI — Value Index (Verdiindeks)</dt>
<dd>Forholdet mellom modellens sannsynlighet og folkemeningen for det anbefalte utfallet: VI = modell% ÷ folk%. Over 1.0 = modellen ser mer verdi enn folkemassen. Bucketer: strong (≥1.5), good (1.25–1.5), neutral (0.9–1.25), weak (&lt;0.9).</dd>
<dt>Edge (pp)</dt>
<dd>Modell% minus NT-folk% for det anbefalte utfallet i prosentpoeng. Positiv = modellen er mer overbevist enn folkemassen. Negativ = folkemassen er mer overbevist enn modellen.</dd>
<dt>CLV — Closing Line Value</dt>
<dd>Prosentvis differanse mellom oddsene på kupongtidspunktet og sluttoddsene (closing odds). Positiv CLV = du fikk bedre odds enn markedet endte på, noe som indikerer langvarig forventningsverdifull betting.</dd>
<dt>PVR — Pool Value Ratio (Pottverdiforhold)</dt>
<dd>PVR = modellens vinnersjanse ÷ folkemassens vinnersjanse for nøyaktig samme kombinasjon. PVR 9x betyr at kombinasjonen er 9x mer unik enn en tilfeldig offentlig kupong — ikke at du får 9x innsatsen tilbake. Høyere PVR gir høyere forventet utdeling ved gevinst.</dd>
<dt>Treff% (Modell-treff)</dt>
<dd>Andel kamper der modellens primæranbefaling stemte med det faktiske utfallet.</dd>
<dt>Dekn% (Systemdekning)</dt>
<dd>Andel kamper der kupongens valgte utfall (inkl. halvdekk/heldekk) dekket det faktiske utfallet.</dd>
<dt>Halvdekk / Heldekk</dt>
<dd>Halvdekk = to utfall valgt for én kamp (e.g. H+U). Heldekk = alle tre utfall valgt. Brukes strategisk for å øke kupongens dekning på usikre kamper.</dd>
<dt>Conviction</dt>
<dd>Singelvalg med konfidens ≥55%. Modellen er overbevist nok til å satse uten backup-utfall.</dd>
<dt>NT-tips</dt>
<dd>Norsk Tippings offentlige prosentandeler — aggregerte valg fra alle spillere på NT-plattformen. Brukes som referansepunkt; fryst ved kupongtidspunkt.</dd>
</dl></div>
""", unsafe_allow_html=True)

_day_labels = {"MIDWEEK": "Midtuke", "SATURDAY": "Lørdag", "SUNDAY": "Søndag"}
def _status_badge(status: str, n_evaluated: int | None = None, n_total: int = 12) -> str:
    if status == "complete":
        return '<span class="badge b-complete">Fullstendig</span>'
    if status == "partial":
        count = f" {n_evaluated}/{n_total}" if n_evaluated is not None else ""
        return f'<span class="badge b-partial" title="Mangler resultater for {n_total - (n_evaluated or 0)} kamp(er). Skriv inn på Resultater-siden.">Delvis{count}</span>'
    return '<span class="badge b-pending" title="Ingen resultater registrert ennå.">Venter</span>'
_strategy_labels = {
    "safe": "Safe", "balanced": "Balansert",
    "value": "Verdi", "jackpot": "Jackpot",
}
_th = ("font-size:9px;font-weight:700;color:#5a7a9a;text-transform:uppercase;"
       "letter-spacing:1.1px;padding:6px 8px;background:rgba(255,255,255,0.04);"
       "border-bottom:1px solid rgba(255,255,255,0.07);white-space:nowrap;")
_td = "padding:5px 8px;color:#c8ddf0;border-bottom:1px solid rgba(255,255,255,0.03);"

evaluated = list_evaluated_coupons()

# ── 1. Evaluerte kuponger ─────────────────────────────────────────────────────

st.markdown('<div class="section-head">Evaluerte kuponger</div>', unsafe_allow_html=True)

if not evaluated:
    st.info(
        "Ingen evaluerte kuponger ennå.\n\n"
        "1. Lagre en kupong på hovedsiden (💾 Lagre kupong)\n"
        "2. Skriv inn kampresultater på **Resultater**-siden\n"
        "3. Evaluering kjøres automatisk, eller manuelt med `python evaluate.py --week <uke> --year <år>`"
    )
else:
    rows_html = ""
    for e in evaluated:
        dl    = _day_labels.get(e.get("day_type", ""), e.get("day_type", "—"))
        hit   = f"{e['hit_rate']*100:.1f}%"   if e.get("hit_rate")   is not None else "—"
        cov   = f"{e['cover_rate']*100:.1f}%" if e.get("cover_rate") is not None else "—"
        all12 = (
            "✓" if e.get("system_covered") == e.get("total_fixtures") == 12
            else ("✗" if e.get("evaluation_status") == "complete" else "—")
        )
        corr  = f"{e['correct_picks']}/{e['total_fixtures']}" if e.get("correct_picks") is not None else "—"
        badge = _status_badge(
            e.get("evaluation_status", ""),
            n_evaluated=e.get("n_matches_evaluated"),
            n_total=e.get("total_fixtures", 12),
        )
        strat = _strategy_labels.get(e.get("strategy") or "", e.get("strategy") or "—")
        pvr   = f"{e['pvr_at_save']:.2f}×" if e.get("pvr_at_save") is not None else "—"
        rows_html += (
            f"<tr>"
            f"<td>{e.get('week','—')}</td>"
            f"<td>{e.get('year','—')}</td>"
            f"<td>{dl}</td>"
            f"<td>{strat}</td>"
            f"<td>{_fmt_nok(e.get('stake_nok') or e.get('budget_nok'))}</td>"
            f"<td style='text-align:right'>{e.get('total_rows','—')}</td>"
            f"<td style='text-align:right'>{corr}</td>"
            f"<td style='text-align:right;font-weight:600;color:#8aaec8'>{hit}</td>"
            f"<td style='text-align:right'>{cov}</td>"
            f"<td style='text-align:right;color:#5a9a6a'>{pvr}</td>"
            f"<td style='text-align:center'>{all12}</td>"
            f"<td>{badge}</td>"
            f"</tr>"
        )
    st.markdown(
        '<table class="hist-table"><thead><tr>'
        "<th>Uke</th><th>År</th><th>Type</th><th>Strategi</th><th>Innsats</th>"
        "<th style='text-align:right'>Rekker</th>"
        "<th style='text-align:right'>Modelltips riktig</th>"
        "<th style='text-align:right'>Modell-treff%</th>"
        "<th style='text-align:right'>Systemdekning%</th>"
        "<th style='text-align:right'>PVR</th>"
        "<th style='text-align:center'>12 rette dekket</th><th>Status</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )

# ── 2. Strategi-ytelse ────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Strategi-ytelse</div>', unsafe_allow_html=True)

_strat_perf = get_strategy_performance()
if not _strat_perf:
    st.markdown(
        '<p style="font-size:11px;color:#1e3448;">Ingen strategi-data ennå. '
        'Kjør <code>python evaluate.py --all</code> etter at resultater er lagret.</p>',
        unsafe_allow_html=True,
    )
else:
    _sp_rows = ""
    for sp in _strat_perf:
        _sn   = _strategy_labels.get(sp.get("strategy") or "", sp.get("strategy") or "—")
        _n    = sp.get("n_coupons", 0)
        _hr   = f"{sp['avg_hit_rate']*100:.1f}%"   if sp.get("avg_hit_rate")   is not None else "—"
        _cr   = f"{sp['avg_cover_rate']*100:.1f}%" if sp.get("avg_cover_rate") is not None else "—"
        _pvr  = f"{sp['avg_pvr']:.2f}×"            if sp.get("avg_pvr")        is not None else "—"
        _pw   = f"{sp['avg_p_win']*100:.2f}%"      if sp.get("avg_p_win")      is not None else "—"
        _jack = sp.get("n_jackpots") or 0
        _nthr = f"{sp['avg_nt_hit_rate']*100:.1f}%" if sp.get("avg_nt_hit_rate") is not None else "—"
        _sp_rows += (
            f"<tr>"
            f"<td style='{_td}font-weight:600'>{_sn}</td>"
            f"<td style='{_td}text-align:right'>{_n}</td>"
            f"<td style='{_td}text-align:right;font-weight:600;color:#8aaec8'>{_hr}</td>"
            f"<td style='{_td}text-align:right'>{_cr}</td>"
            f"<td style='{_td}text-align:right;color:#5a9a6a'>{_pvr}</td>"
            f"<td style='{_td}text-align:right;color:#3a5a78'>{_pw}</td>"
            f"<td style='{_td}text-align:right;color:rgba(200,150,14,.7)'>{_nthr}</td>"
            f"<td style='{_td}text-align:right'>{_jack}</td>"
            f"</tr>"
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr>'
        f'<th style="{_th}text-align:left">Strategi</th>'
        f'<th style="{_th}text-align:right">Kuponger</th>'
        f'<th style="{_th}text-align:right">Treff%</th>'
        f'<th style="{_th}text-align:right">Dekn%</th>'
        f'<th style="{_th}text-align:right">Snitt PVR</th>'
        f'<th style="{_th}text-align:right">P(12/12)</th>'
        f'<th style="{_th}text-align:right">NT-treff%</th>'
        f'<th style="{_th}text-align:right">12/12</th>'
        f'</tr></thead><tbody>{_sp_rows}</tbody></table>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="font-size:10px;color:#1e3448;margin-top:4px;">'
        'NT-treff% = Norsk Tippings folkemening (topptips) sin nøyaktighet, sammenlignet med modellens anbefalte valg.</p>',
        unsafe_allow_html=True,
    )

# ── 3. CDS-validering ─────────────────────────────────────────────────────────

st.markdown('<div class="section-head">CDS-validering (Folkeavvik, fryst snapshot)</div>', unsafe_allow_html=True)
st.markdown(
    '<p style="font-size:10px;color:#3a5a78;margin-bottom:8px;">'
    'CDS = Crowd Disagreement Score — fryst ved kupongtidspunkt. Kuponger lagret før Phase 8 vises ikke her.</p>',
    unsafe_allow_html=True,
)

_cds_rows = get_cds_validation()
_cds_total = sum(r.get("n", 0) for r in _cds_rows)

if _cds_total < 3:
    st.markdown(
        '<p style="font-size:11px;color:#1e3448;">'
        'Ikke nok data ennå. CDS-validering krever kuponger lagret med Phase 8+ og tilhørende resultater.</p>',
        unsafe_allow_html=True,
    )
else:
    _bucket_labels = {"high": "Sterk ≥10pp", "medium": "Moderat 5–10pp", "low": "Lav <5pp"}
    _cds_html = ""
    for brow in _cds_rows:
        _bn   = brow.get("n", 0)
        _nm   = brow.get("n_model") or 0
        _nnt  = brow.get("n_nt")
        _blbl = _bucket_labels.get(brow.get("cds_bucket", ""), brow.get("cds_bucket", "—"))
        _mhr  = _nm / _bn * 100 if _bn > 0 else 0
        _nhr_s = "—"
        _diff_s = "—"
        _diff_c = "#3a5a78"
        if _nnt is not None and _bn > 0:
            _nhr   = _nnt / _bn * 100
            _diff  = _mhr - _nhr
            _nhr_s = f"{_nhr:.0f}%"
            _diff_s = f"{_diff:+.1f}pp"
            _diff_c = "#3aaa78" if _diff > 0 else "#e74c3c"
        _cds_html += (
            f"<tr>"
            f"<td style='{_td}'>{_blbl}</td>"
            f"<td style='{_td}text-align:right;color:#3a5a78'>{_bn}</td>"
            f"<td style='{_td}text-align:right;font-weight:600;color:#8aaec8'>{_mhr:.0f}%</td>"
            f"<td style='{_td}text-align:right;color:rgba(200,150,14,.7)'>{_nhr_s}</td>"
            f"<td style='{_td}text-align:right;font-weight:700;color:{_diff_c}'>{_diff_s}</td>"
            f"</tr>"
        )
    # Totals row
    _all_n   = _cds_total
    _all_nm  = sum(r.get("n_model") or 0 for r in _cds_rows)
    _all_nnt = sum(r.get("n_nt") or 0 for r in _cds_rows if r.get("n_nt") is not None)
    _has_nt  = any(r.get("n_nt") is not None for r in _cds_rows)
    _all_mhr = _all_nm / _all_n * 100 if _all_n > 0 else 0
    _all_nhr_s = f"{_all_nnt/_all_n*100:.0f}%" if _has_nt and _all_n > 0 else "—"
    _all_d = _all_mhr - (_all_nnt / _all_n * 100) if _has_nt and _all_n > 0 else None
    _all_dc = "#3aaa78" if (_all_d or 0) > 0 else "#e74c3c"
    _all_ds = f"{_all_d:+.1f}pp" if _all_d is not None else "—"
    _cds_html += (
        f"<tr style='border-top:1px solid rgba(255,255,255,0.06);'>"
        f"<td style='{_td}font-weight:600'>Totalt</td>"
        f"<td style='{_td}text-align:right;font-weight:600;color:#c8ddf0'>{_all_n}</td>"
        f"<td style='{_td}text-align:right;font-weight:700;color:#8aaec8'>{_all_mhr:.0f}%</td>"
        f"<td style='{_td}text-align:right;color:rgba(200,150,14,.7);font-weight:600'>{_all_nhr_s}</td>"
        f"<td style='{_td}text-align:right;font-weight:800;color:{_all_dc}'>{_all_ds}</td>"
        f"</tr>"
    )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr>'
        f'<th style="{_th}text-align:left">CDS nivå</th>'
        f'<th style="{_th}text-align:right">Kamper</th>'
        f'<th style="{_th}text-align:right">Modell</th>'
        f'<th style="{_th}text-align:right">NT-tips</th>'
        f'<th style="{_th}text-align:right">Diff</th>'
        f'</tr></thead><tbody>{_cds_html}</tbody></table>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="font-size:10px;color:#1e3448;margin-top:4px;">'
        'Diff = modellens fordel i prosentpoeng. Positiv = modellen slo folkemeningen.</p>',
        unsafe_allow_html=True,
    )

# ── 4. Overbevisning vs nødvendige ───────────────────────────────────────────

st.markdown(
    '<div class="section-head">Overbevisning vs nødvendige valg</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p style="font-size:11px;color:#3a5a78;margin-bottom:8px;">'
    'Conviction = singelvalg med konfidens ≥55%. Nødvendig = halvdekk/heldekk for å nå budsjett.</p>',
    unsafe_allow_html=True,
)

_conv_rows = get_conviction_stats()
_conv_total = sum(r.get("n", 0) for r in _conv_rows)

if _conv_total < 3:
    st.markdown(
        '<p style="font-size:11px;color:#1e3448;">'
        'Ikke nok evaluerte kamper ennå.</p>',
        unsafe_allow_html=True,
    )
else:
    _cov_type_labels = {
        "single":     "Singelvalg",
        "half_cover": "Halvdekk",
        "full_cover": "Heldekk",
    }
    _conv_html = ""
    for cr in _conv_rows:
        _n   = cr.get("n", 0)
        _nc  = cr.get("n_correct") or 0
        _ncv = cr.get("n_covered") or 0
        _ict = cr.get("is_conviction")
        _ct  = cr.get("coverage_type", "")
        _lbl = _cov_type_labels.get(_ct, _ct)
        _tag = "Conviction" if _ict else "Standard"
        _hr  = f"{_nc/_n*100:.0f}%" if _n > 0 else "—"
        _cov = f"{_ncv/_n*100:.0f}%" if _n > 0 else "—"
        _conv_html += (
            f"<tr>"
            f"<td style='{_td}'>{_lbl}</td>"
            f"<td style='{_td}color:{'#f5c518' if _ict else '#3a5a78'}'>{_tag}</td>"
            f"<td style='{_td}text-align:right;color:#3a5a78'>{_n}</td>"
            f"<td style='{_td}text-align:right;font-weight:600;color:#8aaec8'>{_hr}</td>"
            f"<td style='{_td}text-align:right'>{_cov}</td>"
            f"</tr>"
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr>'
        f'<th style="{_th}text-align:left">Dekkingstype</th>'
        f'<th style="{_th}text-align:left">Kategori</th>'
        f'<th style="{_th}text-align:right">Kamper</th>'
        f'<th style="{_th}text-align:right">Treff%</th>'
        f'<th style="{_th}text-align:right">Dekket%</th>'
        f'</tr></thead><tbody>{_conv_html}</tbody></table>',
        unsafe_allow_html=True,
    )

# ── 5. Modell vs NT-tips ──────────────────────────────────────────────────────

st.markdown('<div class="section-head">Modell vs NT-folkets topptips</div>', unsafe_allow_html=True)
st.markdown(
    '<p style="font-size:11px;color:#3a5a78;margin-bottom:8px;">'
    'Kun kuponger lagret med Phase 8+ snapshotdata (pub_prob fryst ved lagringstidspunkt).</p>',
    unsafe_allow_html=True,
)

_nt_cmp = get_nt_model_comparison()
_nt_n   = _nt_cmp.get("n_total") or 0

if _nt_n < 3:
    st.markdown(
        '<p style="font-size:11px;color:#1e3448;">'
        'Ikke nok data ennå. Sammenligningen krever kuponger med lagret folkesnapshotdata.</p>',
        unsafe_allow_html=True,
    )
else:
    _nm_n = _nt_cmp.get("n_model") or 0
    _nt_n2 = _nt_cmp.get("n_nt") or 0
    _mhr2 = _nm_n / _nt_n * 100
    _nhr2 = _nt_n2 / _nt_n * 100
    _diff2 = _mhr2 - _nhr2
    _dc2   = "#3aaa78" if _diff2 > 0 else "#e74c3c"
    _m1, _m2, _m3, _m4 = st.columns(4)
    _m1.metric("Kamper evaluert", _nt_n)
    _m2.metric("Modell-treff", f"{_mhr2:.1f}%")
    _m3.metric("NT-tips-treff", f"{_nhr2:.1f}%")
    _m4.metric("Modell-fordel", f"{_diff2:+.1f}pp")
    st.markdown(
        f'<p style="font-size:10px;color:#1e3448;margin-top:2px;">'
        f'Modell = anbefalt pick. NT-tips = Norsk Tippings folkemening (høyeste prosentandel-pick, fryst ved lagring).</p>',
        unsafe_allow_html=True,
    )

# ── 6. PVR vs utdeling ────────────────────────────────────────────────────────

st.markdown('<div class="section-head">PVR vs faktisk utdeling</div>', unsafe_allow_html=True)

_pvr_data = get_pvr_payout_data()

if not _pvr_data:
    st.markdown(
        '<p style="font-size:10px;color:#1e3448;">'
        'Denne seksjonen vises når du registrerer en faktisk gevinst fra NT. '
        'Etter gevinst: oppdater <code>actual_payout_nok</code> i <code>coupon_evaluations</code> '
        'med beløpet NT utbetalte.</p>',
        unsafe_allow_html=True,
    )
else:
    _pvr_html = ""
    for pd in _pvr_data:
        _pvr_v = f"{pd['pvr']:.2f}×" if pd.get("pvr") is not None else "—"
        _pay   = f"{pd['actual_payout_nok']:,.0f} NOK" if pd.get("actual_payout_nok") else "—"
        _hr3   = f"{pd['hit_rate']*100:.1f}%" if pd.get("hit_rate") else "—"
        _cr3   = f"{pd['cover_rate']*100:.1f}%" if pd.get("cover_rate") else "—"
        _strat = _strategy_labels.get(pd.get("strategy") or "", pd.get("strategy") or "—")
        _pvr_html += (
            f"<tr>"
            f"<td style='{_td}'>{pd.get('week','—')}/{pd.get('year','—')}</td>"
            f"<td style='{_td}'>{_strat}</td>"
            f"<td style='{_td}text-align:right;color:#5a9a6a;font-weight:600'>{_pvr_v}</td>"
            f"<td style='{_td}text-align:right;color:#f5c518;font-weight:700'>{_pay}</td>"
            f"<td style='{_td}text-align:right'>{_hr3}</td>"
            f"<td style='{_td}text-align:right'>{_cr3}</td>"
            f"</tr>"
        )
    st.markdown(
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">'
        f'<thead><tr>'
        f'<th style="{_th}text-align:left">Uke/År</th>'
        f'<th style="{_th}text-align:left">Strategi</th>'
        f'<th style="{_th}text-align:right">PVR ved lagring</th>'
        f'<th style="{_th}text-align:right">Faktisk utdeling</th>'
        f'<th style="{_th}text-align:right">Treff%</th>'
        f'<th style="{_th}text-align:right">Dekn%</th>'
        f'</tr></thead><tbody>{_pvr_html}</tbody></table>',
        unsafe_allow_html=True,
    )

# ── Kupongdetaljer ────────────────────────────────────────────────────────────

st.markdown('<div class="section-head">Kupongdetaljer</div>', unsafe_allow_html=True)

all_with_preds = list_coupons_with_predictions()

if not all_with_preds:
    st.markdown(
        '<p style="color:#3a5a78;font-size:12px;">Ingen kuponger med lagrede prediksjoner.</p>',
        unsafe_allow_html=True,
    )
else:
    _strat_lookup = {e["coupon_id"]: e.get("strategy") for e in evaluated}

    def _coupon_label(c: dict) -> str:
        dl = _day_labels.get(c.get("day_type", ""), c.get("day_type", "?"))
        strat_key = _strat_lookup.get(c["coupon_id"])
        strat_s = f" · {_strategy_labels.get(strat_key, strat_key)}" if strat_key else ""
        return f"Uke {c['week']}/{c['year']} — {dl}{strat_s}  ({c['n_predictions']} tips, {c['n_results']} resultater)"

    options = [c["coupon_id"] for c in all_with_preds]
    sel = st.selectbox(
        "Velg kupong",
        options=options,
        format_func=lambda cid: _coupon_label(next(c for c in all_with_preds if c["coupon_id"] == cid)),
    )

    rows    = get_results_for_coupon(sel)
    ev      = get_evaluation(sel)
    clv_map = {r["fixture_id"]: r for r in get_clv_for_coupon(sel)}
    pe_map  = {r["fixture_id"]: r for r in get_pick_evaluations(sel)}

    if ev:
        _col_a, _col_b, _col_c, _col_d = st.columns(4)
        _covered_all = ev.get("system_covered") == ev.get("total_fixtures") == 12
        _col_a.metric("Modelltips riktig", f"{ev.get('correct_picks','—')}/{ev.get('total_fixtures',12)}")
        _col_b.metric("Modell-treff%", f"{ev['hit_rate']*100:.1f}%" if ev.get("hit_rate") is not None else "—")
        _col_c.metric("Systemdekning", f"{ev['cover_rate']*100:.1f}%" if ev.get("cover_rate") is not None else "—")
        _col_d.metric("12 rette dekket", "Ja ✓" if _covered_all else ("Nei" if ev.get("evaluation_status") == "complete" else "—"))

    # CLV summary
    clv_vals = [r["clv_selected"] for r in clv_map.values() if r.get("clv_selected") is not None]
    if clv_vals:
        avg_clv = sum(clv_vals) / len(clv_vals)
        clv_color = "#3aaa78" if avg_clv >= 0 else "#e74c3c"
        st.markdown(
            f'<p style="font-size:11px;color:{clv_color};margin-top:0.5rem;">'
            f'Gjennomsnittlig CLV: <strong>{avg_clv*100:+.1f}%</strong> '
            f'({len(clv_vals)} kamper med avslutningsodds)</p>',
            unsafe_allow_html=True,
        )

    # Per-fixture table — summary columns always visible; analytics in expandable <details>
    detail_rows = ""
    for r in rows:
        fid    = r.get("fixture_id", "")
        result = r.get("result_1x2")
        home_s = r.get("home_score")
        away_s = r.get("away_score")
        score_str = f"{home_s}–{away_s}" if home_s is not None else "—"

        sel_outcomes = r.get("selected_outcomes", [])
        if isinstance(sel_outcomes, str):
            try:
                sel_outcomes = json.loads(sel_outcomes)
            except Exception:
                sel_outcomes = []

        picks_str = " / ".join(sel_outcomes) if sel_outcomes else "—"
        conf_str  = f"{r['confidence']*100:.1f}%" if r.get("confidence") else "—"

        if result and sel_outcomes:
            if result in sel_outcomes:
                picks_cell = f'<span class="pick-covered">{picks_str}</span>'
                check_cell = '<span class="tick" aria-label="Dekket">&#10003;</span>'
            else:
                picks_cell = f'<span class="pick-miss">{picks_str}</span>'
                check_cell = '<span class="cross" aria-label="Ikke dekket">&#10007;</span>'
        else:
            picks_cell = picks_str
            check_cell = "—"

        result_cell = result if result else '<span class="dim">—</span>'

        # ── Analytics panel data ──────────────────────────────────────────────
        odds_h = r.get("odds_h"); odds_u = r.get("odds_u"); odds_b = r.get("odds_b")
        odds_str_ap = (
            f"{odds_h:.2f} / {odds_u:.2f} / {odds_b:.2f}"
            if all(x is not None for x in [odds_h, odds_u, odds_b])
            else "—"
        )

        clv_data = clv_map.get(fid)
        if clv_data and clv_data.get("clv_selected") is not None:
            clv_val  = clv_data["clv_selected"]
            clv_cls  = "pos" if clv_val >= 0 else "neg"
            clv_ap   = f'<span class="ap-val {clv_cls}">{clv_val*100:+.1f}%</span>'
        else:
            clv_ap   = '<span class="ap-val">—</span>'

        pe = pe_map.get(fid)
        if pe:
            _cds_v  = f"{pe['cds']:.1f}pp" if pe.get("cds") is not None else "—"
            _vi_v   = pe.get("vi_bucket") or "—"
            _vi_cls = "pos" if _vi_v in ("strong", "good") else ("neg" if _vi_v == "weak" else "")
            _ep     = pe.get("edge_pp")
            _edge_v = f"{_ep:+.1f}pp" if _ep is not None else "—"
            _edge_cls = "pos" if (_ep or 0) > 0 else ("neg" if (_ep or 0) < 0 else "")
        else:
            _cds_v = _vi_v = _edge_v = "—"
            _vi_cls = _edge_cls = ""

        analytics_panel = (
            f'<div class="ap">'
            f'<span class="ap-item"><span class="ap-lbl">Odds:</span><span class="ap-val">{odds_str_ap}</span></span>'
            f'<span class="ap-item"><span class="ap-lbl">Konf.:</span><span class="ap-val">{conf_str}</span></span>'
            f'<span class="ap-item"><span class="ap-lbl">CDS:</span><span class="ap-val">{_cds_v}</span></span>'
            f'<span class="ap-item"><span class="ap-lbl">VI:</span><span class="ap-val {_vi_cls}">{_vi_v}</span></span>'
            f'<span class="ap-item"><span class="ap-lbl">Edge:</span><span class="ap-val {_edge_cls}">{_edge_v}</span></span>'
            f'<span class="ap-item"><span class="ap-lbl">CLV:</span>{clv_ap}</span>'
            f'</div>'
        )

        detail_rows += (
            f"<tr>"
            f"<td style='color:#3a5a78'>{r['match_number']}</td>"
            f"<td style='white-space:nowrap'>{r.get('home_name','?')} – {r.get('away_name','?')}</td>"
            f"<td style='color:#f5c518;font-weight:700;text-align:center'>{r.get('recommended_pick','—')}</td>"
            f"<td>{picks_cell}</td>"
            f"<td style='text-align:center;font-weight:700'>{result_cell}</td>"
            f"<td style='text-align:center;color:#8ab4d8'>{score_str}</td>"
            f"<td style='text-align:center'>{check_cell}</td>"
            f"<td><details><summary>▾ Analyse</summary>{analytics_panel}</details></td>"
            f"</tr>"
        )

    st.markdown(
        '<table class="detail-table"><thead><tr>'
        "<th>#</th><th>Kamp</th>"
        "<th style='text-align:center'>Tips</th>"
        "<th>Systemvalg</th>"
        "<th style='text-align:center'>Resultat</th>"
        "<th style='text-align:center'>Score</th>"
        "<th style='text-align:center'>Dekket</th>"
        "<th>Analyse</th>"
        f"</tr></thead><tbody>{detail_rows}</tbody></table>",
        unsafe_allow_html=True,
    )

    if not rows:
        st.markdown(
            '<p style="color:#3a5a78;font-size:12px">Ingen prediksjoner funnet.</p>',
            unsafe_allow_html=True,
        )
