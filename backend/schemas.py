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
    p_11: float | None = None
    p_10: float | None = None
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


# ── /v1/signals ───────────────────────────────────────────────────────────────

class MatchSignal(BaseModel):
    match_number: int
    home_team: str
    away_team: str
    fixture_id: str | None = None
    league_name: str | None = None
    kickoff_utc: str | None = None
    recommended_pick: str           # H, U, or B
    model_prob: float               # model probability of recommended pick (0–100)
    pub_prob: float | None = None   # public probability of recommended pick (0–100)
    edge_pp: float | None = None    # model_prob − pub_prob in pp
    crowd_disagreement_score: float | None = None
    value_index: float | None = None
    signal_strength: float = 0.0   # composite ranking score
    has_public_tips: bool = False
    prob_h: float = 0.0
    prob_u: float = 0.0
    prob_b: float = 0.0
    pub_prob_h: float | None = None
    pub_prob_u: float | None = None
    pub_prob_b: float | None = None
    stats_signals: list[str] = []
    classification: str = ""
    home_logo_url: str | None = None
    away_logo_url: str | None = None


class SignalBoardResponse(BaseModel):
    coupon_id: str
    coupon_label: str
    deadline_utc: str
    week: int
    year: int
    signals: list[MatchSignal]


# ── /v1/insights ──────────────────────────────────────────────────────────────

class OddsMovement(BaseModel):
    open_h: float
    open_u: float
    open_b: float
    current_h: float
    current_u: float
    current_b: float
    n_snapshots: int
    direction: str    # "steaming" | "drifting" | "stable"
    bookmaker: str    # e.g. "Pinnacle"


class InsightSignal(BaseModel):
    match_number: int
    home_team: str
    away_team: str
    fixture_id: str | None = None
    league_name: str | None = None
    kickoff_utc: str | None = None
    recommended_pick: str         # H, U, or B — model's argmax
    prob_h: float                 # model probabilities (0–100)
    prob_u: float
    prob_b: float
    model_prob: float             # model prob of recommended pick (0–100)

    # NT public percentages — coupon product only, never used for betting value
    pub_prob_h: float | None = None
    pub_prob_u: float | None = None
    pub_prob_b: float | None = None
    pub_prob: float | None = None
    has_public_tips: bool = False
    edge_pp: float | None = None               # model − pub in pp (coupon layer only)
    crowd_disagreement_score: float | None = None
    value_index: float | None = None

    # 1X2 bookmaker odds and market edge
    odds_h: float | None = None
    odds_u: float | None = None
    odds_b: float | None = None
    odds_source: str | None = None
    implied_prob: float | None = None          # de-vigged bookmaker implied prob of rec pick (0–100)
    market_edge_pp: float | None = None        # model_prob − implied_prob in pp (betting value)

    # Odds movement (Pinnacle snapshots)
    odds_movement: OddsMovement | None = None

    # Poisson model: BTTS
    btts_model_prob: float | None = None       # P(BTTS=yes) from Poisson, 0–100
    btts_yes_odds: float | None = None
    btts_no_odds: float | None = None
    btts_bookmaker: str | None = None
    btts_implied_yes: float | None = None      # de-vigged, 0–100
    btts_market_edge_pp: float | None = None   # btts_model_prob − btts_implied_yes

    # Poisson model: Over/Under 2.5
    over_model_prob: float | None = None       # P(over 2.5) from Poisson, 0–100
    under_model_prob: float | None = None
    over_25_odds: float | None = None
    under_25_odds: float | None = None
    ou_bookmaker: str | None = None
    over_implied: float | None = None          # de-vigged, 0–100
    over_market_edge_pp: float | None = None   # over_model_prob − over_implied

    # Poisson inputs (for transparency)
    xg_home: float | None = None
    xg_away: float | None = None

    # API-Football prediction signals
    # winner/direction
    af_winner_name:     str | None = None   # e.g. "Spain"
    af_winner_pick:     str | None = None   # "H", "U", or "B" (derived from team IDs)
    af_winner_agrees:   bool | None = None  # does AF pick match our model pick?
    af_win_or_draw:     bool | None = None  # double chance flag
    af_under_over:      float | None = None # positive=Over, negative=Under, None=no signal
    af_advice:          str | None = None   # text e.g. "Double chance : Spain or draw"
    # comparison data
    af_poisson_home:    float | None = None # comparison.poisson_distribution.home (%)
    af_poisson_away:    float | None = None # comparison.poisson_distribution.away (%)
    af_goals_home:      float | None = None # comparison.goals.home (%)
    af_goals_away:      float | None = None # comparison.goals.away (%)
    # O/U alignment
    af_ou_agrees:       bool | None = None  # AF under_over direction matches our Poisson O/U call

    # Composite confidence score (0–100)
    confidence_score:   float | None = None


class InsightsResponse(BaseModel):
    coupon_id: str
    coupon_label: str
    deadline_utc: str
    week: int
    year: int
    signals: list[InsightSignal]


# ── /v1/bets/* ────────────────────────────────────────────────────────────────

class PaperBet(BaseModel):
    id: str
    coupon_id: str | None = None
    fixture_id: str
    match_name: str
    league: str | None = None
    kickoff_utc: str | None = None
    market: str
    outcome: str
    bookmaker: str
    ref_odds: float
    implied_prob: float
    model_prob: float
    edge_pp: float
    stake_nok: float
    expected_value: float
    insight_type: str | None = None
    risk_level: str
    reason: str | None = None
    model_quality: str | None = None
    status: str
    result_outcome: str | None = None
    closing_odds: float | None = None
    clv: float | None = None
    profit_nok: float | None = None
    created_at: str
    settled_at: str | None = None


class BankrollPoint(BaseModel):
    bet_index: int
    bankroll_after: float
    label: str
    market: str | None = None
    outcome: str | None = None
    profit_nok: float | None = None
    odds: float | None = None
    settled_at: str | None = None


class BetSummary(BaseModel):
    starting_bankroll: float
    current_bankroll: float
    total_staked: float
    total_profit: float
    roi: float | None = None
    n_won: int
    n_lost: int
    n_pending: int
    hit_rate: float | None = None
    avg_clv: float | None = None
    by_market: dict


class GenerateBetsResponse(BaseModel):
    created: int
    skipped: int
    bets: list[PaperBet]


class ScanResponse(BaseModel):
    scan: dict
    candidates: dict
    duration_s: float
