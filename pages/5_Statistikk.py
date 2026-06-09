"""
Statistikk — API-Football statistical enrichment per fixture.

Shows standings, form, home/away records, goals, and the Phase 5 model output
for each NT fixture.

Phase 5 additions:
  - Model (v5) row: blended probabilities H/U/B
  - vs Bukmeker row: total probability shift from bookmaker prior
  - Verdi vs folket row: (model − public) in pp — pool value signal
  - crowd_disagreement_score badge
  - crowd_pressure_pick tag
  - Audit trail: which signals were active (form / h_a_record / standings / goals)

API-Football is used as a DATA SOURCE only — standings, form, and goals.
AF predictions are NOT used for recommendations.

Populate enrichment by running:
    python sync.py --enrich-fixtures
"""
from datetime import datetime as _dt
import json as _json
import streamlit as st
from db.schema import init_db
from db.coupon import list_coupons
from db.enrichment import get_coupon_enrichment
from models.match import Match as _MatchModel
from analysis.probability import process_match as _bm_prior
from analysis.model import run_model as _run_model
from analysis.estimated_prior import compute_estimated_prior as _est_prior

st.set_page_config(
    page_title="Statistikk — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] {
    background-color: #0b1623 !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
.block-container { max-width: 1180px !important; padding-top: 2.5rem !important; }

.page-title  { font-size:1.4rem; font-weight:900; color:#fff; margin-bottom:0.2rem; }
.page-title .q { color:#f5c518; }
.page-subtitle { font-size:0.75rem; color:#3a5a78; margin-bottom:1.5rem; }
.page-subtitle code { color:#5a7a96; }

/* ── Fixture card ──────────────────────────────────────────────────── */
.fx-card {
    background: rgba(255,255,255,0.025);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 10px;
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
}
.fx-header {
    display: flex; align-items: baseline; gap: 10px;
    margin-bottom: 8px;
}
.fx-num  { font-size:11px; font-weight:700; color:#2e4a64; min-width:28px; }
.fx-teams { font-size:13px; font-weight:700; color:#e0eaf6; flex:1; }
.fx-comp  { font-size:10px; color:#3a5a78; }
.fx-ko    { font-size:10px; color:#2e4a64; white-space:nowrap; }

/* ── Stats table ───────────────────────────────────────────────────── */
.stats-tbl {
    width:100%; border-collapse:collapse;
    font-size:11px; margin-bottom:8px;
}
.stats-tbl th {
    font-size:10px; font-weight:700; color:#3a5a78;
    text-transform:uppercase; letter-spacing:1px;
    padding:4px 8px; border-bottom:1px solid rgba(255,255,255,0.06);
    text-align:left;
}
.stats-tbl th.val { text-align:center; }
.stats-tbl td { padding:3px 8px; color:#c8ddf0; border-bottom:1px solid rgba(255,255,255,0.025); }
.stats-tbl td.lbl { color:#3a5a78; font-size:10px; white-space:nowrap; }
.stats-tbl td.val { text-align:center; }
.stats-tbl tr:last-child td { border-bottom:none; }

/* ── Form badges ────────────────────────────────────────────────────── */
.fb { display:inline-block; font-size:10px; font-weight:700; padding:1px 5px;
      border-radius:3px; margin:0 1px; }
.fb-w { background:#0c2a14; color:#3aaa78; }
.fb-d { background:#1a1e2a; color:#5a7a96; }
.fb-l { background:#2a0c0c; color:#e74c3c; }

/* ── Model Inputs panel ─────────────────────────────────────────────── */
.mi-panel {
    margin-top: 8px;
    padding: 8px 10px;
    background: rgba(245,197,24,0.03);
    border: 1px solid rgba(245,197,24,0.08);
    border-radius: 6px;
}
.mi-header {
    font-size: 9px; font-weight: 700; color: #f5c518;
    text-transform: uppercase; letter-spacing: 1.5px;
    margin-bottom: 6px;
    display: flex; align-items: center; gap: 8px;
}
/* ── Comparison table ─────────────────────────────────────────────── */
.mi-tbl {
    width: 100%; border-collapse: collapse;
    font-size: 11px; margin-bottom: 6px;
}
.mi-tbl th {
    font-size: 9px; color: #2e4a64; font-weight: 700;
    text-transform: uppercase; letter-spacing: 1px;
    padding: 2px 8px; border-bottom: 1px solid rgba(255,255,255,0.04);
    text-align: center;
}
.mi-tbl th.name-col { text-align: left; }
.mi-tbl td { padding: 2px 8px; color: #c8ddf0; border-bottom: 1px solid rgba(255,255,255,0.015); }
.mi-tbl tr:last-child td { border-bottom: none; }
.mi-tbl td.name-col {
    font-size: 9px; color: #3a5a78; text-transform: uppercase;
    letter-spacing: 0.5px; white-space: nowrap;
}
.mi-tbl td.num  { text-align: center; font-weight: 600; }
.mi-tbl td.src  { font-size: 9px; color: #1e3248; padding-left: 4px; white-space: nowrap; }
.mi-tbl tr.mi-sep td { border-top: 1px solid rgba(255,255,255,0.05); padding-top: 4px; }
/* Colour coding per outcome */
.mi-h     { color: #3aaa78; }
.mi-u     { color: #5a7a96; }
.mi-b     { color: #e07a5f; }
/* Differential: positive public > bm (crowd pressure) */
.mi-dpos  { color: #e07a5f; font-weight: 700; }
/* Differential: negative public < bm (potential pool value) */
.mi-dneg  { color: #3aaa78; font-weight: 700; }
.mi-dneut { color: #2e4a64; }
/* ── Model output row ─────────────────────────────────────────────── */
.mi-tbl tr.mi-model td { background: rgba(245,197,24,0.025); }
.mi-model-label { color: #f5c518 !important; font-weight: 700 !important; }
/* ── Interpretation tags ──────────────────────────────────────────── */
.mi-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 5px; }
.mi-tag  { font-size: 9px; font-weight: 600; padding: 2px 7px; border-radius: 3px; }
.mi-tag-aligned { background: rgba(58,170,120,0.08);  color: #3aaa78; }
.mi-tag-over    { background: rgba(224,122,95,0.10);  color: #e07a5f; }
.mi-tag-under   { background: rgba(58,170,120,0.10);  color: #2aaa68; }
.mi-tag-value   { background: rgba(245,197,24,0.10);  color: #f5c518; }
.mi-tag-neutral { background: rgba(255,255,255,0.03); color: #3a5a78; }
.mi-tag-model   { background: rgba(245,197,24,0.12);  color: #f5c518; font-weight: 700; }
.mi-tag-pressure{ background: rgba(224,122,95,0.12);  color: #e07a5f; }
/* ── Crowd disagreement score ─────────────────────────────────────── */
.cds-badge {
    display: inline-block; font-size: 9px; font-weight: 700;
    padding: 1px 6px; border-radius: 3px; margin-left: 4px;
}
.cds-low  { background: rgba(255,255,255,0.04); color: #2e4a64; }
.cds-mid  { background: rgba(200,150,14,0.10);  color: #c8960e; }
.cds-high { background: rgba(245,197,24,0.15);  color: #f5c518; }
/* ── Signal availability row ──────────────────────────────────────── */
.mi-row { display: flex; align-items: baseline; gap: 6px; font-size: 10px; flex-wrap: wrap; }
.mi-sig-lbl  { font-size: 9px; color: #2e4a64; margin-right: 2px; }
.mi-sig-ok   { color: #3aaa78; font-size: 10px; margin-right: 4px; }
.mi-sig-miss { color: #2e4a64; font-size: 10px; margin-right: 4px; text-decoration: line-through; }

/* ── Odds / match footer ─────────────────────────────────────────────── */
.fx-footer {
    display:flex; align-items:center; gap:12px;
    margin-top:6px; font-size:10px; color:#2e4a64;
    flex-wrap: wrap;
}
.fx-odds  { color:#5a7a96; }
.fx-conf  { color:#2e4a64; }
.fx-af-id { color:#1e3248; }

/* ── No AF data notice ──────────────────────────────────────────────── */
.no-af-row {
    font-size:10px; color:#1e3248; font-style:italic;
    padding:6px 0 2px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Statistikk</div>
<div class="page-subtitle">
  Statistisk grunnlag og modellforklaring per kamp: tabellposisjon, form, m&aring;l, odds-prior og NT-tips.
  Modell v5 kombinerer bookmakerodds, API-Football-statistikk og NT-eksperttips.
  Kj&oslash;r <code>python sync.py --enrich-fixtures</code> for &aring; oppdatere.
</div>
""", unsafe_allow_html=True)

init_db()

# ── Load coupons for current week ─────────────────────────────────────────────

iso  = _dt.now().isocalendar()
week = iso.week
year = iso.year

coupons = list_coupons(week=week, year=year)
if not coupons:
    st.info("Ingen kuponger i databasen for denne uken. Kjør `python sync.py` først.")
    st.stop()

# ── Model helper ──────────────────────────────────────────────────────────────

def _compute_model(f: dict) -> tuple["_MatchModel | None", bool]:
    """
    Run the prediction model for one enrichment row.

    Returns (match, is_estimated) where is_estimated=True means the prior
    came from model_estimated_prior (no bookmaker odds available).

    Odds priority (matches data/loader.py::_best_odds so Statistikk and
    Kampanalyse always produce identical model probabilities):
      1. Bookmaker odds from the odds table (any source)
      2. NT expert tips converted to synthetic decimal odds (100 / pct)
      3. Estimated prior from stats (is_estimated=True)
    """
    oh, ou, ob = f.get("odds_h"), f.get("odds_u"), f.get("odds_b")
    odds_src = f.get("odds_source", "")

    # NT expert tips fallback — mirrors data/loader.py::_best_odds() exactly
    if not (oh and ou and ob):
        ex_h = f.get("expert_h"); ex_u = f.get("expert_u"); ex_b = f.get("expert_b")
        if (ex_h and ex_u and ex_b
                and float(ex_h) > 0 and float(ex_u) > 0 and float(ex_b) > 0):
            oh = round(100.0 / float(ex_h), 4)
            ou = round(100.0 / float(ex_u), 4)
            ob = round(100.0 / float(ex_b), 4)
            odds_src = "nt_expert"

    if oh and ou and ob:
        # Normal path: bookmaker odds (or NT expert synthetic) → run Phase 5 model
        try:
            m = _MatchModel(
                number=f["match_number"],
                home_team=f.get("home_name", ""),
                away_team=f.get("away_name", ""),
                odds_h=float(oh), odds_u=float(ou), odds_b=float(ob),
                odds_source=odds_src,
            )
            _bm_prior(m)
            _run_model(m, f)
            return m, False
        except Exception:
            return None, False

    # No bookmaker odds: try estimated prior from stats + NT tips
    # Check DB-stored estimated prior first, then compute on-the-fly
    est = None
    if f.get("estimated_h") is not None:
        # Already stored in DB (via get_coupon_enrichment join)
        try:
            sigs_raw = f.get("estimated_signals") or "[]"
            sigs = _json.loads(sigs_raw) if isinstance(sigs_raw, str) else (sigs_raw or [])
            est = {
                "estimated_h":  float(f["estimated_h"]),
                "estimated_u":  float(f["estimated_u"]),
                "estimated_b":  float(f["estimated_b"]),
                "signals_used": sigs,
                "confidence":   float(f.get("estimated_confidence") or 0.0),
                "source":       "model_estimated",
            }
        except Exception:
            est = None

    if est is None:
        est = _est_prior(f)

    if est is None:
        return None, True

    try:
        m = _MatchModel(
            number=f["match_number"],
            home_team=f.get("home_name", ""),
            away_team=f.get("away_name", ""),
            odds_h=1.0, odds_u=1.0, odds_b=1.0,  # dummy — never used for display
            odds_source="model_estimated",
        )
        m.prob_h     = est["estimated_h"]
        m.prob_u     = est["estimated_u"]
        m.prob_b     = est["estimated_b"]
        m.confidence = est["confidence"]
        m.stats_signals = est["signals_used"]
        m.has_af_data   = any(s in est["signals_used"] for s in ("form", "standings", "goals", "h_a_record"))
        m.has_expert_tips = "nt_expert" in est["signals_used"]

        # Value vs public crowd
        from analysis.model import _get_float
        pb_h = _get_float(f, "public_h")
        pb_u = _get_float(f, "public_u")
        pb_b = _get_float(f, "public_b")
        if pb_h is not None and pb_u is not None and pb_b is not None:
            pb_sum = pb_h + pb_u + pb_b
            if pb_sum > 0:
                pub_h = pb_h / pb_sum
                pub_u = pb_u / pb_sum
                pub_b = pb_b / pb_sum
                m.pub_prob_h = pub_h
                m.pub_prob_u = pub_u
                m.pub_prob_b = pub_b
                m.has_public_tips = True
                m.value_h = round((m.prob_h - pub_h) * 100, 1)
                m.value_u = round((m.prob_u - pub_u) * 100, 1)
                m.value_b = round((m.prob_b - pub_b) * 100, 1)
                m.crowd_disagreement_score = round(
                    (abs(m.value_h) + abs(m.value_u) + abs(m.value_b)) / 2.0, 1
                )
                vals = {"H": m.value_h, "U": m.value_u, "B": m.value_b}
                m.crowd_pressure_pick = min(vals, key=vals.get)

        probs = {"H": m.prob_h, "U": m.prob_u, "B": m.prob_b}
        m.recommendation = max(probs, key=probs.get)
        return m, True
    except Exception:
        return None, True

# ── Helpers ───────────────────────────────────────────────────────────────────

def _form_badges(form: str | None, n: int = 5) -> str:
    if not form:
        return '<span style="color:#2e4a64">—</span>'
    chars = form[-n:] if len(form) > n else form
    parts = []
    for c in chars.upper():
        if c == "W":
            parts.append('<span class="fb fb-w">V</span>')
        elif c == "D":
            parts.append('<span class="fb fb-d">U</span>')
        elif c == "L":
            parts.append('<span class="fb fb-l">T</span>')
    return "".join(parts) if parts else '<span style="color:#2e4a64">—</span>'


def _pos(v) -> str:
    return f"#{v}" if v is not None else "—"


def _goals(gf, ga) -> str:
    if gf is None and ga is None:
        return "—"
    return f"{gf or 0} / {ga or 0}"


def _pct(v) -> str:
    return f"{v*100:.0f}%" if v is not None else "—"


def _odds_label(h, u, b, source, estimated: bool = False) -> str:
    if h is None:
        return '<span style="color:#c8960e">Estimert prior (ingen bukm. odds)</span>' if estimated else "Ingen odds"
    src = (source or "").capitalize()
    return f"{h:.2f} / {u:.2f} / {b:.2f}  [{src}]"


def _implied_probs(odds_h, odds_u, odds_b) -> tuple[float | None, float | None, float | None]:
    if not (odds_h and odds_u and odds_b):
        return None, None, None
    try:
        h, u, b = 1 / odds_h, 1 / odds_u, 1 / odds_b
        total   = h + u + b
        return h / total, u / total, b / total
    except (ZeroDivisionError, TypeError):
        return None, None, None


def _sum_warning(h, u, b) -> str:
    if h is None:
        return ""
    total = (h or 0) + (u or 0) + (b or 0)
    if abs(total - 100) > 2:
        return f' <span style="color:#e74c3c;font-size:9px">⚠ sum={total:.0f}</span>'
    return ""


def _diff_cls(d: float) -> str:
    if d > 5:
        return "mi-dpos"
    if d < -5:
        return "mi-dneg"
    return "mi-dneut"


def _val_cls(v: float) -> str:
    """Value = model − public.  Positive = pool value (green), negative = crowd pressure (red)."""
    if v > 5:
        return "mi-dneg"   # green: crowd underplays vs model → pool value
    if v < -5:
        return "mi-dpos"   # red: crowd overplays vs model → crowd pressure
    return "mi-dneut"


def _ds(d: float) -> str:
    return f"+{d:.0f}" if d >= 0 else f"{d:.0f}"


def _dpp(d: float) -> str:
    return f"{d:+.1f}pp"


def _sig(label: str, ok: bool) -> str:
    cls = "mi-sig-ok" if ok else "mi-sig-miss"
    return f'<span class="{cls}">{label}</span>'


def _cds_cls(score: float) -> str:
    if score >= 25:
        return "cds-high"
    if score >= 12:
        return "cds-mid"
    return "cds-low"


def _generate_tags(bm_h, bm_u, bm_b, pb_h, pb_u, pb_b, ex_h, ex_u, ex_b) -> str:
    tags: list[tuple[str, str]] = []

    if pb_h is not None and bm_h is not None:
        diffs = [
            (round(pb_h - bm_h), "H"),
            (round(pb_u - bm_u), "U"),
            (round(pb_b - bm_b), "B"),
        ]
        max_abs = max(abs(d) for d, _ in diffs)

        if max_abs < 5:
            tags.append(("aligned", "Bookmaker og folket enige"))
        else:
            for diff, out in diffs:
                if diff >= 20:
                    tags.append(("over",  f"Folket sterkt overvurderer {out} (+{diff}pp)"))
                elif diff >= 10:
                    tags.append(("over",  f"Folket overvurderer {out} (+{diff}pp)"))
                elif diff <= -20:
                    tags.append(("under", f"Folket undervurderer {out} ({diff}pp)"))
                    tags.append(("value", f"Mulig poolverdi på {out}"))
                elif diff <= -10:
                    tags.append(("under", f"Folket undervurderer {out} ({diff}pp)"))
                    tags.append(("value", f"Mulig poolverdi på {out}"))

        triples = list(zip([pb_h, pb_u, pb_b], [bm_h, bm_u, bm_b], ["H", "U", "B"]))
        bm_fav  = max(triples, key=lambda t: t[1])[2]
        for pb_v, bm_v, out in triples:
            if out == bm_fav and pb_v - bm_v > 15:
                tags.append(("neutral", f"Favoritt ({out}) tungt spilt av folket"))

    if ex_h is not None and bm_h is not None:
        for ex_v, bm_v, out in [
            (ex_h, bm_h, "H"), (ex_u, bm_u, "U"), (ex_b, bm_b, "B")
        ]:
            diff = round(ex_v - bm_v)
            if abs(diff) >= 10:
                tags.append(("value", f"Ekspert avviker fra bm på {out} ({_ds(diff)}pp)"))

    if not tags:
        return ""

    _cls_map = {
        "aligned": "mi-tag-aligned", "over": "mi-tag-over",
        "under":   "mi-tag-under",   "value": "mi-tag-value",
        "neutral": "mi-tag-neutral",
    }
    parts = [
        f'<span class="mi-tag {_cls_map.get(t, "mi-tag-neutral")}">{txt}</span>'
        for t, txt in tags
    ]
    return f'<div class="mi-tags">{"".join(parts)}</div>'


def _build_mi_panel(
    f: dict,
    model_match: _MatchModel | None = None,
    is_estimated: bool = False,
) -> str:
    """
    Build the full Model Inputs HTML panel for one fixture.

    f             — enrichment dict from get_coupon_enrichment()
    model_match   — Match object after run_model(); None when odds are missing
    is_estimated  — True when the prior came from model_estimated_prior
    """
    imp_h, imp_u, imp_b = _implied_probs(
        f.get("odds_h"), f.get("odds_u"), f.get("odds_b")
    )
    odds_src = (f.get("odds_source") or "").capitalize()
    bm_h = round(imp_h * 100) if imp_h is not None else None
    bm_u = round(imp_u * 100) if imp_u is not None else None
    bm_b = round(imp_b * 100) if imp_b is not None else None

    ex_h = f.get("expert_h"); ex_u = f.get("expert_u"); ex_b = f.get("expert_b")
    pb_h = f.get("public_h"); pb_u = f.get("public_u"); pb_b = f.get("public_b")

    ex_warn = _sum_warning(ex_h, ex_u, ex_b)
    pb_warn = _sum_warning(pb_h, pb_u, pb_b)

    def _cell(v, cls=""):
        s = f"{round(v)}" if v is not None else "—"
        return f'<td class="num {cls}">{s}</td>'

    # ── Bookmaker row (or estimated prior notice) ─────────────────────────────
    if bm_h is not None:
        bm_cells = _cell(bm_h, "mi-h") + _cell(bm_u, "mi-u") + _cell(bm_b, "mi-b")
        bm_src   = f'<td class="src">[{odds_src}]</td>'
        bm_row_label = "Bukmeker (odds-prior)"
    elif is_estimated and model_match is not None:
        # Show estimated prior values in the bookmaker slot, clearly labelled
        eh = round(model_match.prob_h * 100)
        eu = round(model_match.prob_u * 100)
        eb = round(model_match.prob_b * 100)
        bm_cells = _cell(eh, "mi-h") + _cell(eu, "mi-u") + _cell(eb, "mi-b")
        bm_src   = '<td class="src" style="color:#c8960e">[estimert]</td>'
        bm_row_label = (
            '<span style="color:#c8960e;font-weight:700">'
            'Estimert prior basert p&aring; statistikk'
            '</span>'
        )
    else:
        bm_cells = '<td class="num" colspan="3" style="color:#2e4a64">Ingen odds tilgjengelig</td>'
        bm_src   = "<td></td>"
        bm_row_label = "Bukmeker (odds-prior)"

    # ── Expert row ────────────────────────────────────────────────────────────
    if ex_h is not None:
        ex_cells = _cell(ex_h, "mi-h") + _cell(ex_u, "mi-u") + _cell(ex_b, "mi-b")
    else:
        ex_cells = '<td class="num" colspan="3" style="color:#2e4a64">—</td>'

    # ── Public row ────────────────────────────────────────────────────────────
    if pb_h is not None:
        pb_cells = _cell(pb_h, "mi-h") + _cell(pb_u, "mi-u") + _cell(pb_b, "mi-b")
    else:
        pb_cells = '<td class="num" colspan="3" style="color:#2e4a64">—</td>'

    # ── Folket vs bookmaker differential ─────────────────────────────────────
    diff_row = ""
    if bm_h is not None and pb_h is not None:
        dh = round(pb_h - bm_h); du = round(pb_u - bm_u); db = round(pb_b - bm_b)
        diff_row = (
            f'<tr class="mi-sep">'
            f'<td class="name-col">Folket vs bm</td>'
            f'<td class="num {_diff_cls(dh)}">{_ds(dh)}</td>'
            f'<td class="num {_diff_cls(du)}">{_ds(du)}</td>'
            f'<td class="num {_diff_cls(db)}">{_ds(db)}</td>'
            f'<td></td>'
            f'</tr>'
        )

    # ── Ekspert vs bookmaker differential ────────────────────────────────────
    exp_diff_row = ""
    if bm_h is not None and ex_h is not None:
        edh = round(ex_h - bm_h); edu = round(ex_u - bm_u); edb = round(ex_b - bm_b)
        exp_diff_row = (
            f'<tr>'
            f'<td class="name-col">Ekspert vs bm</td>'
            f'<td class="num {_diff_cls(edh)}">{_ds(edh)}</td>'
            f'<td class="num {_diff_cls(edu)}">{_ds(edu)}</td>'
            f'<td class="num {_diff_cls(edb)}">{_ds(edb)}</td>'
            f'<td></td>'
            f'</tr>'
        )

    # ── Phase 5 Model output rows ─────────────────────────────────────────────
    model_section = ""
    model_tags_html = ""
    if model_match is not None and not is_estimated:
        # Normal path: show full model output vs bookmaker prior
        mh = round(model_match.prob_h * 100, 1)
        mu = round(model_match.prob_u * 100, 1)
        mb = round(model_match.prob_b * 100, 1)

        # Model row (gold-tinted background)
        model_row = (
            f'<tr class="mi-sep mi-model">'
            f'<td class="name-col mi-model-label">Modell (v5)</td>'
            f'<td class="num mi-h">{mh}</td>'
            f'<td class="num mi-u">{mu}</td>'
            f'<td class="num mi-b">{mb}</td>'
            f'<td class="src">[v5]</td>'
            f'</tr>'
        )

        # vs Bukmeker row — total probability shift from bookmaker prior
        vs_bm_row = ""
        if bm_h is not None:
            adj_h = round(model_match.prob_h * 100 - bm_h, 1)
            adj_u = round(model_match.prob_u * 100 - bm_u, 1)
            adj_b = round(model_match.prob_b * 100 - bm_b, 1)
            vs_bm_row = (
                f'<tr>'
                f'<td class="name-col">vs Bukmeker</td>'
                f'<td class="num {_diff_cls(adj_h)}">{_dpp(adj_h)}</td>'
                f'<td class="num {_diff_cls(adj_u)}">{_dpp(adj_u)}</td>'
                f'<td class="num {_diff_cls(adj_b)}">{_dpp(adj_b)}</td>'
                f'<td></td>'
                f'</tr>'
            )

        # Verdi vs folket row — pool value signal
        value_row = ""
        if model_match.has_public_tips and model_match.value_h is not None:
            vh = model_match.value_h
            vu = model_match.value_u
            vb = model_match.value_b
            value_row = (
                f'<tr class="mi-sep">'
                f'<td class="name-col">Verdi vs folket</td>'
                f'<td class="num {_val_cls(vh)}">{_dpp(vh)}</td>'
                f'<td class="num {_val_cls(vu)}">{_dpp(vu)}</td>'
                f'<td class="num {_val_cls(vb)}">{_dpp(vb)}</td>'
                f'<td></td>'
                f'</tr>'
            )

        model_section = model_row + vs_bm_row + value_row

        # Crowd disagreement badge + tags
        cds_html = ""
        if model_match.crowd_disagreement_score is not None:
            cds  = model_match.crowd_disagreement_score
            cls  = _cds_cls(cds)
            cds_html = (
                f'<span class="cds-badge {cls}">'
                f'Uenighet: {cds:.0f}pp'
                f'</span>'
            )

        crowd_tags = []
        if model_match.crowd_pressure_pick:
            pick   = model_match.crowd_pressure_pick
            v_pick = {"H": model_match.value_h, "U": model_match.value_u,
                      "B": model_match.value_b}.get(pick, 0.0) or 0.0
            if v_pick < -10:
                crowd_tags.append(
                    f'<span class="mi-tag mi-tag-pressure">'
                    f'Folkepres på {pick} ({_dpp(v_pick)})</span>'
                )

        if model_match.recommendation:
            rec   = model_match.recommendation
            v_rec = {"H": model_match.value_h, "U": model_match.value_u,
                     "B": model_match.value_b}.get(rec, 0.0) or 0.0
            if v_rec > 10:
                crowd_tags.append(
                    f'<span class="mi-tag mi-tag-value">'
                    f'Poolverdi: {rec} underspilt ({_dpp(v_rec)})</span>'
                )

        # Signal audit: which stats signals were active
        sig_names = {
            "form":       "Form",
            "h_a_record": "Hjem/borte",
            "standings":  "Tabell",
            "goals":      "Mål",
        }
        if model_match.stats_signals:
            used_tags = " ".join(
                f'<span class="mi-tag mi-tag-aligned">{sig_names.get(s, s)}</span>'
                for s in model_match.stats_signals
            )
            model_tags_html += f'<div class="mi-tags" style="margin-top:3px;">{used_tags}</div>'

        if cds_html or crowd_tags:
            model_tags_html += (
                f'<div class="mi-tags" style="margin-top:3px;">'
                + cds_html
                + "".join(crowd_tags)
                + "</div>"
            )

    elif is_estimated and model_match is not None:
        # Estimated prior path: show which signals were used + value vs public
        sig_names = {
            "form":       "Form",
            "h_a_record": "Hjem/borte",
            "standings":  "Tabell",
            "goals":      "Mål",
            "nt_expert":  "NT ekspert",
        }

        # Verdi vs folket (estimated model vs public tips)
        value_row = ""
        if model_match.has_public_tips and model_match.value_h is not None:
            vh = model_match.value_h
            vu = model_match.value_u
            vb = model_match.value_b
            value_row = (
                f'<tr class="mi-sep">'
                f'<td class="name-col">Verdi vs folket</td>'
                f'<td class="num {_val_cls(vh)}">{_dpp(vh)}</td>'
                f'<td class="num {_val_cls(vu)}">{_dpp(vu)}</td>'
                f'<td class="num {_val_cls(vb)}">{_dpp(vb)}</td>'
                f'<td></td>'
                f'</tr>'
            )
        model_section = value_row

        # Signal audit tags
        if model_match.stats_signals:
            used_tags = " ".join(
                f'<span class="mi-tag mi-tag-aligned">{sig_names.get(s, s)}</span>'
                for s in model_match.stats_signals
            )
            model_tags_html += f'<div class="mi-tags" style="margin-top:3px;">{used_tags}</div>'

        # Crowd disagreement + pressure tags
        cds_html = ""
        if model_match.crowd_disagreement_score is not None:
            cds = model_match.crowd_disagreement_score
            cds_html = (
                f'<span class="cds-badge {_cds_cls(cds)}">'
                f'Uenighet: {cds:.0f}pp'
                f'</span>'
            )

        crowd_tags = []
        if model_match.crowd_pressure_pick:
            pick   = model_match.crowd_pressure_pick
            v_pick = {"H": model_match.value_h, "U": model_match.value_u,
                      "B": model_match.value_b}.get(pick, 0.0) or 0.0
            if v_pick < -10:
                crowd_tags.append(
                    f'<span class="mi-tag mi-tag-pressure">'
                    f'Folkepres på {pick} ({_dpp(v_pick)})</span>'
                )

        if cds_html or crowd_tags:
            model_tags_html += (
                f'<div class="mi-tags" style="margin-top:3px;">'
                + cds_html + "".join(crowd_tags) + "</div>"
            )

    table = f"""<table class="mi-tbl">
  <tr>
    <th class="name-col"></th>
    <th>H%</th><th>U%</th><th>B%</th><th></th>
  </tr>
  <tr>
    <td class="name-col">{bm_row_label}</td>
    {bm_cells}{bm_src}
  </tr>
  <tr>
    <td class="name-col">NT Ekspert{ex_warn}</td>
    {ex_cells}<td></td>
  </tr>
  <tr>
    <td class="name-col">NT Folket{pb_warn}</td>
    {pb_cells}<td></td>
  </tr>
  {diff_row}
  {exp_diff_row}
  {model_section}
</table>"""

    tags = _generate_tags(bm_h, bm_u, bm_b, pb_h, pb_u, pb_b, ex_h, ex_u, ex_b)

    # Statistical signal availability
    has_form     = bool(f.get("home_last_5") or f.get("away_last_5"))
    has_standing = f.get("home_position") is not None or f.get("away_position") is not None
    has_ha       = bool(f.get("home_home_record") or f.get("away_away_record"))
    has_goals    = f.get("home_goals_for") is not None or f.get("away_goals_for") is not None
    sig_row = (
        f'<div class="mi-row">'
        f'<span class="mi-sig-lbl">Datakilder:</span>'
        + _sig("Form", has_form)
        + _sig("Tabell", has_standing)
        + _sig("Hjemme/borte", has_ha)
        + _sig("Mål", has_goals)
        + "</div>"
    )

    # Confidence badge (model output)
    conf_badge = ""
    if model_match is not None:
        conf_val = round(model_match.confidence * 100, 1)
        badge_bg  = "rgba(200,150,14,0.10)" if is_estimated else "rgba(245,197,24,0.08)"
        badge_col = "#c8960e"               if is_estimated else "#f5c518"
        conf_badge = (
            f'<span style="font-size:9px;font-weight:700;padding:1px 6px;'
            f'border-radius:3px;background:{badge_bg};color:{badge_col};'
            f'margin-left:6px;">'
            f'Konf. {conf_val:.1f}%</span>'
        )

    if is_estimated:
        header_label = f'Modellinput &mdash; Estimert prior (ingen bukm. odds){conf_badge}'
    else:
        header_label = f'Modellinput &mdash; Verdianalyse{conf_badge}'

    return (
        '<div class="mi-panel">'
        f'<div class="mi-header">{header_label}</div>'
        + table + tags + model_tags_html + sig_row
        + "</div>"
    )


def _fmt_kickoff(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        d = _dt.fromisoformat(iso_str)
        return d.strftime("%d.%m %H:%M")
    except Exception:
        return iso_str[:16]


# ── Coupon tabs ───────────────────────────────────────────────────────────────

_day_labels = {"midtuke": "Midtuke", "lordag": "Lordag", "sondag": "Sondag"}
tab_labels  = [_day_labels.get(c["coupon_id"].split("-")[0], c["label"]) for c in coupons]
tabs = st.tabs(tab_labels)

for tab, coupon in zip(tabs, coupons):
    with tab:
        fixtures = get_coupon_enrichment(coupon["coupon_id"])
        if not fixtures:
            st.info("Ingen kamper funnet for denne kupongen.")
            continue

        n_enriched = sum(1 for f in fixtures if f.get("has_api_football_data"))
        n_total    = len(fixtures)

        st.markdown(
            f'<div style="font-size:10px;color:#2e4a64;margin-bottom:8px;">'
            f'{n_enriched}/{n_total} kamper beriket med API-Football-data</div>',
            unsafe_allow_html=True,
        )

        for f in fixtures:
            num    = f["match_number"]
            home   = f["home_name"]
            away   = f["away_name"]
            comp   = f.get("arrangement_name") or f.get("competition_id") or ""
            ko     = _fmt_kickoff(f.get("kickoff_utc", ""))
            has_af = bool(f.get("has_api_football_data"))

            # Compute model output once per fixture (used by _build_mi_panel)
            model_match, is_estimated = _compute_model(f)

            # ── Card header ──────────────────────────────────────────────
            header_html = (
                f'<div class="fx-header">'
                f'<span class="fx-num">#{num}</span>'
                f'<span class="fx-teams">{home} <span style="color:#2e4a64">vs</span> {away}</span>'
                f'<span class="fx-comp">{comp}</span>'
                f'<span class="fx-ko">{ko}</span>'
                f'</div>'
            )

            if not has_af:
                no_af_msg = (
                    '<div class="no-af-row">'
                    'Ingen API-Football-data (tabellposisjon/form ikke tilgjengelig).'
                    '</div>'
                )
                mi_html_no_af = _build_mi_panel(f, model_match, is_estimated)
                footer_no_af = (
                    f'<div class="fx-footer">'
                    f'<span class="fx-odds">Odds: {_odds_label(f.get("odds_h"), f.get("odds_u"), f.get("odds_b"), f.get("odds_source"))}</span>'
                    f'</div>'
                )
                st.markdown(
                    f'<div class="fx-card">{header_html}{no_af_msg}{mi_html_no_af}{footer_no_af}</div>',
                    unsafe_allow_html=True,
                )
                continue

            # ── Stats table ───────────────────────────────────────────────
            lg_name   = f.get("league_name") or ""
            pos_h     = _pos(f.get("home_position"))
            pos_a     = _pos(f.get("away_position"))
            form_h    = _form_badges(f.get("home_last_5"), 5)
            form_a    = _form_badges(f.get("away_last_5"), 5)
            rec_h     = f.get("home_home_record") or "—"
            rec_a     = f.get("away_away_record") or "—"
            goals_h   = _goals(f.get("home_goals_for"), f.get("home_goals_against"))
            goals_a   = _goals(f.get("away_goals_for"), f.get("away_goals_against"))

            table_html = f"""
<table class="stats-tbl">
  <tr>
    <th></th>
    <th class="val">{home}</th>
    <th class="val">{away}</th>
  </tr>
  <tr>
    <td class="lbl">Posisjon</td>
    <td class="val">{pos_h}</td>
    <td class="val">{pos_a}</td>
  </tr>
  <tr>
    <td class="lbl">Form (siste 5)</td>
    <td class="val">{form_h}</td>
    <td class="val">{form_a}</td>
  </tr>
  <tr>
    <td class="lbl">Hjemme / Borte rekord</td>
    <td class="val" title="Hjemmekamper">{rec_h}</td>
    <td class="val" title="Bortekamper">{rec_a}</td>
  </tr>
  <tr>
    <td class="lbl">Mal (for/mot totalt)</td>
    <td class="val">{goals_h}</td>
    <td class="val">{goals_a}</td>
  </tr>
</table>"""

            # ── Model Inputs panel ─────────────────────────────────────────
            mi_html = _build_mi_panel(f, model_match, is_estimated)

            # ── Footer ────────────────────────────────────────────────────
            conf     = f.get("match_confidence")
            conf_str = f"Konfidans {conf:.0%}" if conf is not None else ""
            af_id    = f.get("api_football_fixture_id")
            af_id_str = f"AF #{af_id}" if af_id else ""
            lg_str   = f"{lg_name}  " if lg_name else ""

            footer_html = (
                f'<div class="fx-footer">'
                f'<span class="fx-odds">Odds: {_odds_label(f.get("odds_h"), f.get("odds_u"), f.get("odds_b"), f.get("odds_source"), estimated=is_estimated)}</span>'
                f'<span class="fx-conf">{conf_str}</span>'
                f'<span class="fx-af-id">{lg_str}{af_id_str}</span>'
                f'</div>'
            )

            st.markdown(
                f'<div class="fx-card">{header_html}{table_html}{mi_html}{footer_html}</div>',
                unsafe_allow_html=True,
            )
