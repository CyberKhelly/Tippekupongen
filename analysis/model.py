"""
Phase 5: Unified Prediction Engine.

Pipeline for each fixture:
  1. Bookmaker prior  — vig-normalized implied probabilities (always the anchor,
                        always ≥ 87% of the final probability in any scenario)
  2. Stats adjustment — form + home/away record + standings + goals → home_edge
                        applied as a bounded ±_MAX_ADJ shift on H/B only
  3. Value detection  — model vs NT public tips → per-outcome value scores
                        + crowd_disagreement_score (TVD × 100)

Entry point:  run_model(match, enrichment)
  process_match() must be called first to set the initial bookmaker prior.
  run_model() then reads match.prob_h/u/b as the prior and overwrites them
  with the final model output. All intermediate values are stored on Match
  for full auditability.

Architecture invariant:
  NT public/expert percentages must NOT influence match.prob_h/u/b.
  They are used only in Step 3 (value detection), never as model inputs.

─── Draw probability note ──────────────────────────────────────────────────
The stats adjustment (home_edge) only redistributes probability between H
and B. Draw probability is intentionally left unchanged by the stats signal.

TODO Phase 5B+: extend _compute_stats_signal() to return a draw_edge as a
second value (float ∈ [−1, +1]) representing evidence that a draw is more
or less likely than the bookmaker implies. Candidate signals:
  • Form similarity  — similar recent form → higher draw probability
  • Defensive strength (goals against) — both teams concede few → more draws
  • xG similarity  — closely matched xG profiles → higher draw probability
When implemented, apply draw_edge as a bounded adjustment (suggested cap:
±_MAX_ADJ_DRAW = 0.04) by redistributing between U and the trailing of H/B.
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from models.match import Match

_MAX_ADJ = 0.08   # maximum |stats adjustment| on H (opposite applied to B)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def run_model(match: Match, enrichment: dict | None) -> None:
    """
    Run the unified prediction engine for one fixture.

    Reads the bookmaker prior from match.prob_h/u/b (set by process_match),
    applies available signals, and overwrites match.prob_h/u/b and
    match.confidence with the final model output.

    Stores full audit trail on the match object:
      match.bm_prob_h/u/b        — bookmaker prior snapshot
      match.home_edge            — composite stats edge (−1 to +1)
      match.stats_adj_pp         — signed pp applied to H (opposite on B)
      match.stats_signals        — list of signal names that contributed
      match.has_af_data          — True if any AF stats signal was used
      match.pub_prob_h/u/b       — normalised public tip fractions
      match.value_h/u/b          — (model − public) in pp
      match.crowd_disagreement_score — TVD(model, public) × 100
      match.crowd_pressure_pick  — outcome most overplayed by public vs model
      match.has_public_tips      — True if crowd signals were computed

    NT public/expert percentages do NOT affect model probability.
    expert_adj_h/u/b and has_expert_tips are kept as zero/False for
    backward compat with the fixture_model_output table schema.
    """
    # ── Step 1: snapshot bookmaker prior ─────────────────────────────────────
    bm_h, bm_u, bm_b = match.prob_h, match.prob_u, match.prob_b
    match.bm_prob_h = bm_h
    match.bm_prob_u = bm_u
    match.bm_prob_b = bm_b

    base_h, base_u, base_b = bm_h, bm_u, bm_b

    # ── Step 2: stats adjustment (only when AF enrichment is available) ───────
    if enrichment:
        home_edge, signals_used = _compute_stats_signal(enrichment)
        match.home_edge     = round(home_edge, 4)
        match.stats_signals = signals_used

        if signals_used:
            adj  = home_edge * _MAX_ADJ
            match.stats_adj_pp = round(adj * 100, 2)   # +pp = home boosted
            # Clamp to a small positive floor before normalising: if the
            # adjustment exceeds the bookmaker's small probability for one
            # outcome, unclamped arithmetic would produce a negative value
            # that carries through as an impossible probability after division.
            sa_h = max(1e-6, bm_h + adj)
            sa_b = max(1e-6, bm_b - adj)
            sa_u = max(1e-6, bm_u)                       # draw unchanged by adj
            t    = sa_h + sa_u + sa_b
            base_h, base_u, base_b = sa_h / t, sa_u / t, sa_b / t
            match.has_af_data = True

    # ── Final model output ────────────────────────────────────────────────────
    match.prob_h     = base_h
    match.prob_u     = base_u
    match.prob_b     = base_b
    match.confidence = max(base_h, base_u, base_b)
    probs = {"H": base_h, "U": base_u, "B": base_b}
    match.recommendation = max(probs, key=probs.get)

    # ── Step 4: value detection (requires public tips) ────────────────────────
    pb_h = _get_float(enrichment, "public_h")
    pb_u = _get_float(enrichment, "public_u")
    pb_b = _get_float(enrichment, "public_b")

    if pb_h is not None and pb_u is not None and pb_b is not None:
        pb_sum = pb_h + pb_u + pb_b
        if pb_sum > 0:
            pub_h = pb_h / pb_sum
            pub_u = pb_u / pb_sum
            pub_b = pb_b / pb_sum

            match.pub_prob_h     = pub_h
            match.pub_prob_u     = pub_u
            match.pub_prob_b     = pub_b
            match.has_public_tips = True

            v_h = (base_h - pub_h) * 100
            v_u = (base_u - pub_u) * 100
            v_b = (base_b - pub_b) * 100
            match.value_h = round(v_h, 1)
            match.value_u = round(v_u, 1)
            match.value_b = round(v_b, 1)

            # Total variation distance (0–50 pp): measures overall model/crowd disagreement
            match.crowd_disagreement_score = round(
                (abs(v_h) + abs(v_u) + abs(v_b)) / 2.0, 1
            )
            # Outcome most overplayed by public vs model (most negative value)
            vals = {"H": v_h, "U": v_u, "B": v_b}
            match.crowd_pressure_pick = min(vals, key=vals.get)


# ─────────────────────────────────────────────────────────────────────────────
# Stats signal computation
# ─────────────────────────────────────────────────────────────────────────────

def _compute_stats_signal(enrichment: dict) -> tuple[float, list[str]]:
    """
    Derive home_edge ∈ [−1, +1] from available API-Football signals.

    home_edge > 0  →  home team favoured by stats (H prob up, B prob down)
    home_edge < 0  →  away team favoured (H prob down, B prob up)

    Component weights (renormalised across whichever signals are present):
      form        0.35   — last-5 result points fraction per team
      h/a record  0.30   — home team's home record vs away team's away record
      standings   0.25   — table position gap (higher = lower number)
      goals       0.10   — season goal-difference differential

    ── Extension point: xG (Phase 5B+) ────────────────────────────────────────
    When xG columns are added to fixture_stat_enrichment, add a block here:

        h_xg_for = _get_float(enrichment, "home_xg_for_5")
        h_xg_ag  = _get_float(enrichment, "home_xg_against_5")
        a_xg_for = _get_float(enrichment, "away_xg_for_5")
        a_xg_ag  = _get_float(enrichment, "away_xg_against_5")
        if all(v is not None for v in (h_xg_for, h_xg_ag, a_xg_for, a_xg_ag)):
            xg_diff = max(-1.0, min(1.0,
                ((h_xg_for - h_xg_ag) - (a_xg_for - a_xg_ag)) / 2.0
            ))
            components.append((0.35, xg_diff))
            signals.append("xg")
        # When xG is active, consider reducing form weight from 0.35 to 0.25
        # since xG is a stronger recent-form proxy.

    DB columns to add (via ALTER TABLE ADD COLUMN in a future _DDL_PHASE5B_COLUMNS):
        home_xg_for_5       REAL   -- xG scored, last 5 matches
        home_xg_against_5   REAL
        away_xg_for_5       REAL
        away_xg_against_5   REAL
        home_xg_for_season  REAL   -- season totals (lower noise)
        home_xg_against_season REAL
        away_xg_for_season  REAL
        away_xg_against_season REAL
    ────────────────────────────────────────────────────────────────────────────
    """
    components: list[tuple[float, float]] = []   # (weight, edge_value)
    signals:    list[str]                 = []

    # ── Form (last 5 results) ─────────────────────────────────────────────────
    hf = _form_score(enrichment.get("home_last_5"))
    af = _form_score(enrichment.get("away_last_5"))
    if hf is not None and af is not None:
        components.append((0.35, hf - af))
        signals.append("form")

    # ── Home/Away record (disabled for WC — neutral venues, API scheduling artifact) ──
    _is_wc = int(enrichment.get("api_football_league_id") or 0) == 1
    if not _is_wc:
        hha = _record_score(enrichment.get("home_home_record"))
        aaw = _record_score(enrichment.get("away_away_record"))
        if hha is not None and aaw is not None:
            components.append((0.30, hha - aaw))
            signals.append("h_a_record")

    # ── Standings ─────────────────────────────────────────────────────────────
    h_pos = enrichment.get("home_position")
    a_pos = enrichment.get("away_position")
    if h_pos is not None and a_pos is not None:
        # Lower number = higher in table; positive diff = home is higher
        pos_diff = max(-1.0, min(1.0, (int(a_pos) - int(h_pos)) / 20.0))
        components.append((0.25, pos_diff))
        signals.append("standings")

    # ── Goal difference ───────────────────────────────────────────────────────
    hgf = _get_float(enrichment, "home_goals_for")
    hga = _get_float(enrichment, "home_goals_against")
    agf = _get_float(enrichment, "away_goals_for")
    aga = _get_float(enrichment, "away_goals_against")
    if all(v is not None for v in (hgf, hga, agf, aga)):
        home_gd = hgf - hga
        away_gd = agf - aga
        gd_diff = max(-1.0, min(1.0, (home_gd - away_gd) / 30.0))
        components.append((0.10, gd_diff))
        signals.append("goals")

    if not components:
        return 0.0, []

    total_w   = sum(w for w, _ in components)
    home_edge = sum(w * v for w, v in components) / total_w
    return max(-1.0, min(1.0, home_edge)), signals


# ─────────────────────────────────────────────────────────────────────────────
# Signal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _form_score(s: str | None, n: int = 5) -> float | None:
    """
    Convert a form string like 'WWDLW' to a fraction of maximum points (0–1).
    W = 3 pts, D = 1 pt, L = 0 pts.  Uses the most recent n results.
    Returns None when the string is absent or empty.
    """
    if not s:
        return None
    tail    = s.upper()[-n:]
    max_pts = len(tail) * 3
    if max_pts == 0:
        return None
    pts = sum(3 if c == "W" else 1 if c == "D" else 0 for c in tail)
    return pts / max_pts


def _record_score(s: str | None) -> float | None:
    """
    Parse a home/away record string produced by enrich_fixtures._record(),
    format 'W{w} D{d} L{l}' (e.g. 'W4 D2 L1'), and return the fraction of
    possible points earned (0–1).

    Returns None when the string is absent, empty, or has zero total games.
    """
    if not s:
        return None
    try:
        wm = re.search(r"W(\d+)", s)
        dm = re.search(r"D(\d+)", s)
        lm = re.search(r"L(\d+)", s)
        w  = int(wm.group(1)) if wm else 0
        d  = int(dm.group(1)) if dm else 0
        l  = int(lm.group(1)) if lm else 0
    except Exception:
        return None
    total = w + d + l
    return (3 * w + d) / (3 * total) if total > 0 else None


def _get_float(d: dict | None, key: str) -> float | None:
    """Safely extract a float from a dict, returning None on any failure."""
    if not d:
        return None
    v = d.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
