"""
Team Review — admin page for inspecting NT-sourced team identity.

Shows:
  1. Teams needing gender/age_group confirmation (flagged during NT ingestion)
  2. All NT-sourced teams (nt_team_id IS NOT NULL)
  3. All manually-seeded teams (nt_team_id IS NULL)

Read-only. To fix a team, run the SQL shown in the review section or:
    python sync.py --review
"""
import json
import streamlit as st

from db.connection import get_conn
from db.schema import init_db

st.set_page_config(
    page_title="Team Review — TippeQpongen",
    page_icon="⚽",
    layout="wide",
)

# ── CSS ──────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0b1623; }
[data-testid="stHeader"] {
    background-color: #0b1623 !important;
    border-bottom: 1px solid rgba(255,255,255,0.04) !important;
}
.block-container {
    max-width: 1280px !important;
    padding-top: 2.5rem !important;
}
.page-title {
    font-size: 1.4rem;
    font-weight: 900;
    color: #ffffff;
    letter-spacing: -0.2px;
    margin-bottom: 0.3rem;
}
.page-title .q { color: #f5c518; }
.page-subtitle {
    font-size: 0.75rem;
    color: #3a5a78;
    margin-bottom: 1.5rem;
}
.section-head {
    font-size: 0.65rem;
    font-weight: 700;
    color: #2e4a64;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    margin-bottom: 0.5rem;
    margin-top: 1.2rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
    padding-bottom: 0.3rem;
}
.badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
}
.badge-review  { background: #3d2600; color: #f5a623; }
.badge-verified{ background: #0c2a14; color: #3aaa78; }
.badge-no-nt   { background: #0c1e34; color: #5a7a96; }
.team-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'Segoe UI', system-ui, Arial, sans-serif;
    font-size: 11.5px;
}
.team-table th {
    font-size: 9px;
    font-weight: 700;
    color: #2e4a64;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    padding: 6px 8px;
    background: rgba(255,255,255,0.04);
    border-bottom: 1px solid rgba(255,255,255,0.07);
    text-align: left;
    white-space: nowrap;
}
.team-table td {
    padding: 5px 8px;
    color: #c8ddf0;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    vertical-align: middle;
}
.team-table tr:nth-child(even) td { background: rgba(255,255,255,0.02); }
.team-table .dim { color: #3a5a78; }
.fix-box {
    background: #0c1420;
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 6px;
    padding: 10px 14px;
    font-family: 'Courier New', monospace;
    font-size: 11px;
    color: #6ab0d8;
    margin-top: 0.5rem;
    margin-bottom: 1rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="page-title">Tippe<span class="q">Q</span>pongen — Team Review</div>
<div class="page-subtitle">Read-only view of team identity data. Run sync.py --review for terminal output.</div>
""", unsafe_allow_html=True)

# ── Data loading ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def _load_review_teams() -> list[dict]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT detail, logged_at FROM coupon_log
               WHERE event = 'new_team_needs_review'
               ORDER BY logged_at DESC"""
        ).fetchall()
    result = []
    seen = set()
    for row in rows:
        try:
            d = json.loads(row["detail"] or "{}")
        except Exception:
            continue
        tid = d.get("team_id", "")
        if tid in seen:
            continue
        seen.add(tid)
        d["logged_at"] = row["logged_at"][:10] if row["logged_at"] else ""
        result.append(d)
    return result


@st.cache_data(ttl=30)
def _load_nt_teams() -> list[dict]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT team_id, name_local, name_canonical, nt_team_id, betradar_id,
                      gender, age_group, team_type, country_iso
               FROM teams WHERE nt_team_id IS NOT NULL
               ORDER BY name_local"""
        ).fetchall()
    return [dict(r) for r in rows]


@st.cache_data(ttl=30)
def _load_manual_teams() -> list[dict]:
    init_db()
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT team_id, name_local, name_canonical, nt_team_id, betradar_id,
                      gender, age_group, team_type, country_iso
               FROM teams WHERE nt_team_id IS NULL
               ORDER BY name_local"""
        ).fetchall()
    return [dict(r) for r in rows]


review_teams  = _load_review_teams()
nt_teams      = _load_nt_teams()
manual_teams  = _load_manual_teams()

# ── Review teams set for badge lookups ───────────────────────────────────────────
review_team_ids = {t["team_id"] for t in review_teams}


# ── Helper: render a team table ──────────────────────────────────────────────────

def _badge(status: str) -> str:
    if status == "review":
        return '<span class="badge badge-review">Needs Review</span>'
    if status == "verified":
        return '<span class="badge badge-verified">Verified</span>'
    return '<span class="badge badge-no-nt">No NT ID</span>'


def _val(v, fallback: str = "—") -> str:
    if v is None or v == "":
        return f'<span class="dim">{fallback}</span>'
    return str(v)


def _render_team_table(teams: list[dict], badge_fn) -> str:
    if not teams:
        return '<p style="color:#3a5a78;font-size:12px;">None.</p>'
    rows = ""
    for t in teams:
        rows += (
            f"<tr>"
            f"<td>{_val(t.get('name_local'))}</td>"
            f"<td><code style='font-size:10px;color:#8ab4d8'>{_val(t.get('team_id'))}</code></td>"
            f"<td><code style='font-size:10px;color:#5a9abf'>{_val(t.get('nt_team_id'))}</code></td>"
            f"<td>{_val(t.get('betradar_id'))}</td>"
            f"<td>{_val(t.get('gender'))}</td>"
            f"<td>{_val(t.get('age_group'))}</td>"
            f"<td>{_val(t.get('team_type'))}</td>"
            f"<td>{_val(t.get('country_iso'))}</td>"
            f"<td>{badge_fn(t)}</td>"
            f"</tr>"
        )
    return (
        '<table class="team-table">'
        "<thead><tr>"
        "<th>Name (local)</th><th>team_id slug</th><th>NT team ID</th>"
        "<th>BetRadar ID</th><th>Gender</th><th>Age group</th>"
        "<th>Type</th><th>Country</th><th>Status</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )


# ── Section 1: Teams needing review ──────────────────────────────────────────────

st.markdown('<div class="section-head">1 — Teams needing gender / age_group confirmation</div>',
            unsafe_allow_html=True)

if not review_teams:
    st.markdown('<p style="color:#3aaa78;font-size:12px;">No teams pending review.</p>',
                unsafe_allow_html=True)
else:
    st.markdown(
        f'<p style="color:#f5a623;font-size:12px;">'
        f'{len(review_teams)} team(s) were auto-created with uncertain context. '
        f'Verify gender and age_group are correct, then update if needed.</p>',
        unsafe_allow_html=True,
    )

    rows_html = ""
    for t in review_teams:
        rows_html += (
            f"<tr>"
            f"<td>{_val(t.get('name_local'))}</td>"
            f"<td><code style='font-size:10px;color:#5a9abf'>{_val(t.get('nt_team_id'))}</code></td>"
            f"<td>{_val(t.get('betradar_id'))}</td>"
            f"<td style='color:#f5a623'>{_val(t.get('inferred_gender'))}</td>"
            f"<td style='color:#f5a623'>{_val(t.get('inferred_age_group'))}</td>"
            f"<td style='color:#5a7a96'>{_val(t.get('arrangement_name'))}</td>"
            f"<td><code style='font-size:10px;color:#8ab4d8'>{_val(t.get('team_id'))}</code></td>"
            f"<td>{_val(t.get('logged_at'))}</td>"
            f"<td>{_badge('review')}</td>"
            f"</tr>"
        )

    html = (
        '<table class="team-table">'
        "<thead><tr>"
        "<th>Name (NT)</th><th>NT team ID</th><th>BetRadar ID</th>"
        "<th>Inferred gender</th><th>Inferred age</th>"
        "<th>Arrangement (context)</th><th>Auto-generated slug</th>"
        "<th>First seen</th><th>Status</th>"
        "</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        "</table>"
    )
    st.markdown(html, unsafe_allow_html=True)

    st.markdown(
        '<div class="fix-box">'
        "-- To correct a team's gender or age_group:<br>"
        "UPDATE teams SET gender='women', age_group='senior' WHERE nt_team_id='&lt;id&gt;';<br><br>"
        "-- Then re-validate:<br>"
        "python sync.py --validate"
        "</div>",
        unsafe_allow_html=True,
    )

# ── Section 2: NT-sourced teams ──────────────────────────────────────────────────

st.markdown(f'<div class="section-head">2 — NT-sourced teams ({len(nt_teams)} total, nt_team_id IS NOT NULL)</div>',
            unsafe_allow_html=True)

def _badge_nt(t: dict) -> str:
    return _badge("review" if t["team_id"] in review_team_ids else "verified")

st.markdown(_render_team_table(nt_teams, _badge_nt), unsafe_allow_html=True)

# ── Section 3: Manually-seeded teams ─────────────────────────────────────────────

with st.expander(f"3 — Manual / seed teams ({len(manual_teams)} total, no NT ID)", expanded=False):
    st.markdown(
        '<p style="color:#3a5a78;font-size:11px;margin-bottom:8px;">'
        'These teams came from the flat-file TEAM_REGISTRY (ingestion/seed.py). '
        'They will gain an nt_team_id automatically the next time NT returns them in the API response.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(_render_team_table(manual_teams, lambda t: _badge("no-nt")), unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────────

st.markdown("""
<div style="font-size:0.72rem;color:#2e4a64;margin-top:2rem;border-top:1px solid rgba(255,255,255,0.05);padding-top:0.75rem;">
This page refreshes every 30 seconds. Changes made via SQL take effect on next refresh.
Run <code style="color:#5a7a96">python sync.py --review</code> for a terminal summary.
</div>
""", unsafe_allow_html=True)
