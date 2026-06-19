// Mirrors the Pydantic schemas in backend/schemas.py exactly.

export interface CouponListItem {
  coupon_id: string;
  label: string;
  day_type: "MIDWEEK" | "SATURDAY" | "SUNDAY" | null;
  deadline_utc: string;
  week: number;
  year: number;
  n_fixtures: number;
}

export interface CouponMatchRaw {
  match_number: number;
  home_team: string;
  away_team: string;
  odds_h: number | null;
  odds_u: number | null;
  odds_b: number | null;
  odds_source: string | null;
  expert_h: number | null;
  expert_u: number | null;
  expert_b: number | null;
  public_h: number | null;
  public_u: number | null;
  public_b: number | null;
  fixture_id: string | null;
  kickoff_utc: string | null;
}

export interface CouponDetail {
  coupon_id: string;
  label: string;
  deadline_utc: string;
  week: number;
  year: number;
  matches: CouponMatchRaw[];
}

export interface MatchResult {
  match_number: number;
  home_team: string;
  away_team: string;
  picks: string[];
  coverage_type: "single" | "half_cover" | "full_cover";
  recommendation: string;
  odds_h: number;
  odds_u: number;
  odds_b: number;
  odds_source: string;
  prob_h: number;
  prob_u: number;
  prob_b: number;
  confidence: number;
  classification: string;
  bm_prob_h: number;
  bm_prob_u: number;
  bm_prob_b: number;
  home_edge: number;
  stats_adj_pp: number;
  stats_signals: string[];
  has_af_data: boolean;
  pub_prob_h: number | null;
  pub_prob_u: number | null;
  pub_prob_b: number | null;
  has_public_tips: boolean;
  value_h: number | null;
  value_u: number | null;
  value_b: number | null;
  crowd_disagreement_score: number | null;
  crowd_pressure_pick: string | null;
  vi: number | null;
  is_conviction: boolean;
}

export interface CouponShape {
  n_singles: number;
  n_halvdekk: number;
  n_heldekk: number;
}

export interface PayoutSimulation {
  n_winning_sims: number;
  p_win_simulated: number;
  min: number;
  p10: number;
  median: number;
  p90: number;
  p99: number;
  max: number;
  mean: number;
  e_winners: number;
  narrative: string;
}

export interface OptimizeResponse {
  coupon_id: string;
  strategy: string;
  budget: number;
  cost_per_row: number;
  total_rows: number;
  total_cost: number;
  p_win: number;
  pvr: number | null;
  shape: CouponShape;
  matches: MatchResult[];
  payout: PayoutSimulation | null;
}

export type Strategy = "safe" | "balanced" | "jackpot";

export interface SyncStatus {
  last_nt_refresh_at: string | null;
  last_odds_refresh_at: string | null;
  last_full_sync_at: string | null;
  is_running: boolean;
  current_job: string | null;
  last_success: boolean | null;
  last_error: string | null;
  next_nt_refresh_at: string | null;
  next_odds_refresh_at: string | null;
  updated_coupon_ids: string[];
  n_public_pct_changes: number;
  turnover: Record<string, number>;
}
