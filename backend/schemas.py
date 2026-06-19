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


class SyncAccepted(BaseModel):
    accepted: bool
    message: str
