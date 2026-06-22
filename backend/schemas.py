"""Pydantic request/response schemas for the TippeQpongen FastAPI."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# ── /v1/coupons ───────────────────────────────────────────────────────────────

class CouponListItem(BaseModel):
    coupon_id: str
    label: str
    day_type: str | None
    deadline_utc: str
    week: int
    year: int
    n_fixtures: int


class CouponMatchRaw(BaseModel):
    match_number: int
    home_team: str
    away_team: str
    odds_h: float | None
    odds_u: float | None
    odds_b: float | None
    odds_source: str | None
    expert_h: float | None
    expert_u: float | None
    expert_b: float | None
    public_h: float | None
    public_u: float | None
    public_b: float | None
    fixture_id: str | None
    kickoff_utc: str | None


class CouponDetail(BaseModel):
    coupon_id: str
    label: str
    deadline_utc: str
    week: int
    year: int
    matches: list[CouponMatchRaw]


# ── /v1/optimize ──────────────────────────────────────────────────────────────

class OptimizeRequest(BaseModel):
    coupon_id: str
    strategy: Literal["safe", "balanced", "jackpot"] = "balanced"
    budget: float = 192.0
    cost_per_row: float = 1.0
    omsetning: float | None = None


class MatchResult(BaseModel):
    match_number: int
    home_team: str
    away_team: str

    # Picks & coverage
    picks: list[str]        # e.g. ["H"] | ["H","U"] | ["H","U","B"]
    coverage_type: str      # "single" | "half_cover" | "full_cover"
    recommendation: str     # highest model-probability outcome

    # Raw input odds
    odds_h: float
    odds_u: float
    odds_b: float
    odds_source: str

    # Final model probabilities (after stats adjustment + expert blend)
    prob_h: float
    prob_u: float
    prob_b: float
    confidence: float       # max(prob_h, prob_u, prob_b)
    classification: str     # banker|uncertain|full_cover|half_cover|standard

    # Bookmaker prior snapshot (before any adjustment)
    bm_prob_h: float
    bm_prob_u: float
    bm_prob_b: float

    # Stats adjustment from API-Football
    home_edge: float
    stats_adj_pp: float
    stats_signals: list[str]
    has_af_data: bool

    # NT public tip percentages (normalised fractions, 0–1)
    pub_prob_h: float | None
    pub_prob_u: float | None
    pub_prob_b: float | None
    has_public_tips: bool

    # Value: (model_prob − public_prob) × 100 per outcome
    value_h: float | None
    value_u: float | None
    value_b: float | None

    # Crowd signals
    crowd_disagreement_score: float | None   # TVD × 100, 0–50
    crowd_pressure_pick: str | None          # most overplayed outcome

    # Value index for the recommended pick: model_prob / pub_prob
    vi: float | None

    # True when |value_of_rec| >= 10pp and public tips are available
    is_conviction: bool

    # 0–4: number of AF stat signals active (standings/form/h_a_record/goals)
    data_coverage: int


class CouponShape(BaseModel):
    n_singles: int
    n_halvdekk: int
    n_heldekk: int


class PayoutSimulation(BaseModel):
    n_winning_sims: int
    p_win_simulated: float
    min: int
    p10: int
    median: int
    p90: int
    p99: int
    max: int
    mean: int
    e_winners: int
    narrative: str


class OptimizeResponse(BaseModel):
    coupon_id: str
    strategy: str
    budget: float
    cost_per_row: float
    total_rows: int
    total_cost: float
    p_win: float
    pvr: float | None
    shape: CouponShape
    matches: list[MatchResult]
    payout: PayoutSimulation | None


# ── /v1/sync/* ────────────────────────────────────────────────────────────────

class SyncStatus(BaseModel):
    last_nt_refresh_at: str | None
    last_odds_refresh_at: str | None
    last_full_sync_at: str | None
    is_running: bool
    current_job: str | None
    last_success: bool | None
    last_error: str | None
    next_nt_refresh_at: str | None
    next_odds_refresh_at: str | None
    updated_coupon_ids: list[str]
    n_public_pct_changes: int
    turnover: dict[str, float]
    last_freeze_at: str | None = None
    last_freeze_count: int = 0
    last_freeze_coupon_ids: list[str] = []


class SyncAccepted(BaseModel):
    accepted: bool
    message: str


# ── /v1/history/* ─────────────────────────────────────────────────────────────

class HistoryCouponItem(BaseModel):
    coupon_id: str
    week: int
    year: int
    day_type: str | None
    label: str
    deadline_utc: str
    strategy: str | None
    budget_nok: float | None
    total_rows: int
    p_win_at_save: float | None
    pvr_at_save: float | None
    correct_picks: int | None
    total_fixtures: int
    system_covered: int | None
    hit_rate: float | None
    cover_rate: float | None
    n_matches_evaluated: int | None
    evaluation_status: str
    actual_payout_nok: float | None
    n_predictions: int | None


class HistoryPickItem(BaseModel):
    match_number: int
    fixture_id: str
    home_name: str
    away_name: str
    recommended_pick: str
    selected_outcomes: list[str]
    coverage_type: str
    confidence: float
    implied_prob_h: float
    implied_prob_u: float
    implied_prob_b: float
    odds_h: float | None
    odds_u: float | None
    odds_b: float | None
    odds_source: str | None
    pub_prob_h: float | None
    pub_prob_u: float | None
    pub_prob_b: float | None
    value_h: float | None
    value_u: float | None
    value_b: float | None
    cds: float | None
    result_1x2: str | None
    home_score: int | None
    away_score: int | None
    covered: int | None
    model_correct: int | None
    nt_correct: int | None
    cds_bucket: str | None
    value_rec: float | None
    vi_bucket: str | None
    edge_pp: float | None
    is_conviction: int | None


class HistoryCouponDetail(HistoryCouponItem):
    picks: list[HistoryPickItem]


class StrategyPerformance(BaseModel):
    strategy: str
    n_coupons: int
    avg_hit_rate: float | None
    avg_cover_rate: float | None
    n_jackpots: int
    avg_pvr: float | None
    avg_p_win: float | None
    avg_nt_hit_rate: float | None


class CdsValidationBucket(BaseModel):
    cds_bucket: str
    n: int
    n_model: int
    n_nt: int | None


class ConvictionStat(BaseModel):
    is_conviction: int
    coverage_type: str
    n: int
    n_correct: int
    n_covered: int


class NtComparison(BaseModel):
    n_total: int
    n_model: int
    n_nt: int


# ── /v1/coupons/{coupon_id}/enrichment ───────────────────────────────────────

class RecentMatch(BaseModel):
    fixture_id:     int | None = None
    date:           str | None = None
    venue:          str | None = None   # "home" | "away"
    result:         str | None = None   # "W" | "D" | "L"
    score_for:      int | None = None
    score_against:  int | None = None
    opponent_id:    int | None = None
    opponent_name:  str | None = None
    opponent_logo:  str | None = None


class MatchEnrichment(BaseModel):
    match_number: int
    fixture_id: str | None
    home_team: str
    away_team: str
    league_name: str | None
    has_api_football_data: bool
    # Standings: position, form, records, goals
    home_position: int | None
    away_position: int | None
    home_last_5: str | None
    away_last_5: str | None
    home_last_10: str | None
    away_last_10: str | None
    home_home_record: str | None
    away_away_record: str | None
    home_goals_for: int | None
    home_goals_against: int | None
    away_goals_for: int | None
    away_goals_against: int | None
    api_prediction_home: float | None
    api_prediction_draw: float | None
    api_prediction_away: float | None
    api_prediction_advice: str | None
    # Phase 10 — standings
    home_points: int | None
    away_points: int | None
    home_played: int | None
    away_played: int | None
    home_wins: int | None
    home_draws: int | None
    home_losses: int | None
    away_wins: int | None
    away_draws: int | None
    away_losses: int | None
    home_logo_url: str | None
    away_logo_url: str | None
    # Phase 10 — per-match averages
    home_avg_goals_for: float | None
    away_avg_goals_for: float | None
    home_avg_goals_against: float | None
    away_avg_goals_against: float | None
    # Phase 10 — clean sheets and streaks
    home_clean_sheets: int | None
    away_clean_sheets: int | None
    home_streak_wins: int | None
    away_streak_wins: int | None
    home_streak_draws: int | None
    away_streak_draws: int | None
    home_streak_losses: int | None
    away_streak_losses: int | None
    # Phase 10 — AF comparison ratings (0.0–1.0)
    api_comparison_att_home: float | None
    api_comparison_att_away: float | None
    api_comparison_def_home: float | None
    api_comparison_def_away: float | None
    api_comparison_form_home: float | None
    api_comparison_form_away: float | None
    api_comparison_total_home: float | None
    api_comparison_total_away: float | None
    # Phase 11 — per-match recent form for pip tooltips
    home_recent_matches: list[RecentMatch] | None = None
    away_recent_matches: list[RecentMatch] | None = None
    # Phase 12 — aggregated fixture stats (possession, shots, corners, etc.)
    home_recent_fixture_stats: dict | None = None
    away_recent_fixture_stats: dict | None = None
    # Phase 13 — real league size + venue-specific goal averages / clean sheets
    league_size: int | None = None
    home_avg_goals_for_home: float | None = None
    home_avg_goals_against_home: float | None = None
    away_avg_goals_for_away: float | None = None
    away_avg_goals_against_away: float | None = None
    home_clean_sheets_home: int | None = None
    away_clean_sheets_away: int | None = None


# ── /v1/analytics/strategy (Phase 9) ─────────────────────────────────────────

class GenerationAnalytics(BaseModel):
    strategy: str
    n_total: int
    n_evaluated: int
    avg_hits: float | None = None
    avg_pvr: float | None = None
    avg_p_win: float | None = None
    hit_rate_9: float | None = None
    hit_rate_10: float | None = None
    hit_rate_11: float | None = None
    hit_rate_12: float | None = None
    roi: float | None = None


# ── /v1/analytics/generations ─────────────────────────────────────────────────

class GenerationPickResult(BaseModel):
    match_number: int
    fixture_id: str
    home_name: str
    away_name: str
    pick: str
    selected_outcomes: list[str]
    coverage_type: str
    confidence: float | None = None
    result_1x2: str | None = None
    home_score: int | None = None
    away_score: int | None = None
    covered: bool | None = None


class GenerationSummary(BaseModel):
    generation_id: str
    coupon_id: str
    coupon_label: str
    week: int
    year: int
    day_type: str | None = None
    deadline_utc: str
    strategy: str
    budget: float
    row_count: int
    p_win: float | None = None
    pvr: float | None = None
    n_singles: int = 0
    n_halvdekk: int = 0
    n_heldekk: int = 0
    frozen_at: str | None = None
    status: str
    evaluation_status: str
    correct_picks: int | None = None
    all_correct: int = 0
    actual_payout_nok: float | None = None
    evaluated_at: str | None = None


class GenerationDetail(GenerationSummary):
    picks: list[GenerationPickResult] = []
    n_total: int = 0
    n_evaluated: int = 0
