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

  // 0–4: standings / form / h_a_record / goals
  data_coverage: number;
}

export interface CouponShape {
  n_singles: number;
  n_halvdekk: number;
  n_heldekk: number;
}

export interface PayoutSimulation {
  n_winning_sims: number;
  p_win_simulated: number;
  p_11?: number | null;
  p_10?: number | null;
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

// ── History ───────────────────────────────────────────────────────────────────

export interface HistoryCouponItem {
  coupon_id: string;
  week: number;
  year: number;
  day_type: "MIDWEEK" | "SATURDAY" | "SUNDAY" | null;
  label: string;
  deadline_utc: string;
  strategy: string | null;
  budget_nok: number | null;
  total_rows: number;
  p_win_at_save: number | null;
  pvr_at_save: number | null;
  correct_picks: number | null;
  total_fixtures: number;
  system_covered: number | null;
  hit_rate: number | null;
  cover_rate: number | null;
  n_matches_evaluated: number | null;
  evaluation_status: string;
  actual_payout_nok: number | null;
  n_predictions: number | null;
}

export interface HistoryPickItem {
  match_number: number;
  fixture_id: string;
  home_name: string;
  away_name: string;
  recommended_pick: string;
  selected_outcomes: string[];
  coverage_type: string;
  confidence: number;
  implied_prob_h: number;
  implied_prob_u: number;
  implied_prob_b: number;
  odds_h: number | null;
  odds_u: number | null;
  odds_b: number | null;
  odds_source: string | null;
  pub_prob_h: number | null;
  pub_prob_u: number | null;
  pub_prob_b: number | null;
  value_h: number | null;
  value_u: number | null;
  value_b: number | null;
  cds: number | null;
  result_1x2: string | null;
  home_score: number | null;
  away_score: number | null;
  covered: number | null;
  model_correct: number | null;
  nt_correct: number | null;
  cds_bucket: string | null;
  value_rec: number | null;
  vi_bucket: string | null;
  edge_pp: number | null;
  is_conviction: number | null;
}

export interface HistoryCouponDetail extends HistoryCouponItem {
  picks: HistoryPickItem[];
}

export interface StrategyPerformance {
  strategy: string;
  n_coupons: number;
  avg_hit_rate: number | null;
  avg_cover_rate: number | null;
  n_jackpots: number;
  avg_pvr: number | null;
  avg_p_win: number | null;
  avg_nt_hit_rate: number | null;
}

export interface CdsValidationBucket {
  cds_bucket: string;
  n: number;
  n_model: number;
  n_nt: number | null;
}

export interface ConvictionStat {
  is_conviction: number;
  coverage_type: string;
  n: number;
  n_correct: number;
  n_covered: number;
}

export interface NtComparison {
  n_total: number;
  n_model: number;
  n_nt: number;
}

// ── /v1/coupons/{coupon_id}/enrichment ───────────────────────────────────────

// Phase 12 — aggregated /fixtures/statistics over last N completed fixtures
export interface RecentFixtureStats {
  sample_size: number;
  fixture_ids_used: number[];
  avg_possession: number | null;
  avg_shots_on_goal: number | null;
  avg_total_shots: number | null;
  avg_corners: number | null;
  avg_fouls: number | null;
  avg_yellow_cards: number | null;
  avg_red_cards: number | null;
  avg_pass_accuracy: number | null;
  avg_xg: number | null;
}

export interface RecentMatch {
  fixture_id:    number | null;
  date:          string | null;   // "YYYY-MM-DD"
  venue:         "home" | "away" | null;
  result:        "W" | "D" | "L" | null;
  score_for:     number | null;
  score_against: number | null;
  opponent_id:   number | null;
  opponent_name: string | null;
  opponent_logo: string | null;
}

export interface MatchEnrichment {
  match_number: number;
  fixture_id: string | null;
  home_team: string;
  away_team: string;
  league_name: string | null;
  has_api_football_data: boolean;
  // Standings: position, form, H/A record, goal totals
  home_position: number | null;
  away_position: number | null;
  home_last_5: string | null;
  away_last_5: string | null;
  home_last_10: string | null;
  away_last_10: string | null;
  home_home_record: string | null;
  away_away_record: string | null;
  home_goals_for: number | null;
  home_goals_against: number | null;
  away_goals_for: number | null;
  away_goals_against: number | null;
  api_prediction_home: number | null;
  api_prediction_draw: number | null;
  api_prediction_away: number | null;
  api_prediction_advice: string | null;
  // Phase 10 — standings
  home_points: number | null;
  away_points: number | null;
  home_played: number | null;
  away_played: number | null;
  home_wins: number | null;
  home_draws: number | null;
  home_losses: number | null;
  away_wins: number | null;
  away_draws: number | null;
  away_losses: number | null;
  home_logo_url: string | null;
  away_logo_url: string | null;
  // Phase 10 — per-match averages
  home_avg_goals_for: number | null;
  away_avg_goals_for: number | null;
  home_avg_goals_against: number | null;
  away_avg_goals_against: number | null;
  // Phase 10 — clean sheets and streaks
  home_clean_sheets: number | null;
  away_clean_sheets: number | null;
  home_streak_wins: number | null;
  away_streak_wins: number | null;
  home_streak_draws: number | null;
  away_streak_draws: number | null;
  home_streak_losses: number | null;
  away_streak_losses: number | null;
  // Phase 10 — AF comparison ratings (0.0–1.0)
  api_comparison_att_home: number | null;
  api_comparison_att_away: number | null;
  api_comparison_def_home: number | null;
  api_comparison_def_away: number | null;
  api_comparison_form_home: number | null;
  api_comparison_form_away: number | null;
  api_comparison_total_home: number | null;
  api_comparison_total_away: number | null;
  // Phase 11 — per-match recent form for pip tooltips (null when not yet fetched)
  home_recent_matches: RecentMatch[] | null;
  away_recent_matches: RecentMatch[] | null;
  // Phase 12 — aggregated fixture stats (null when competition not covered)
  home_recent_fixture_stats: RecentFixtureStats | null;
  away_recent_fixture_stats: RecentFixtureStats | null;
  // Phase 13 — real league size + venue-specific goal averages / clean sheets
  league_size: number | null;
  home_avg_goals_for_home: number | null;
  home_avg_goals_against_home: number | null;
  away_avg_goals_for_away: number | null;
  away_avg_goals_against_away: number | null;
  home_clean_sheets_home: number | null;
  away_clean_sheets_away: number | null;
}

// ── Phase 9 — generation list + detail ───────────────────────────────────────

export interface GenerationPickResult {
  match_number: number;
  fixture_id: string;
  home_name: string;
  away_name: string;
  pick: string;
  selected_outcomes: string[];
  coverage_type: string;
  confidence: number | null;
  result_1x2: string | null;
  home_score: number | null;
  away_score: number | null;
  covered: boolean | null;
}

export interface GenerationSummary {
  generation_id: string;
  coupon_id: string;
  coupon_label: string;
  week: number;
  year: number;
  day_type: "MIDWEEK" | "SATURDAY" | "SUNDAY" | null;
  deadline_utc: string;
  strategy: string;
  budget: number;
  row_count: number;
  p_win: number | null;
  pvr: number | null;
  n_singles: number;
  n_halvdekk: number;
  n_heldekk: number;
  frozen_at: string | null;
  status: string;
  evaluation_status: string;
  correct_picks: number | null;
  all_correct: number;
  actual_payout_nok: number | null;
  evaluated_at: string | null;
}

export interface GenerationDetail extends GenerationSummary {
  picks: GenerationPickResult[];
  n_total: number;
  n_evaluated: number;
}

// ── Phase 9 — generation analytics ───────────────────────────────────────────

export interface GenerationAnalytics {
  strategy: string;
  n_total: number;
  n_evaluated: number;
  avg_hits: number | null;
  avg_pvr: number | null;
  avg_p_win: number | null;
  hit_rate_9: number | null;
  hit_rate_10: number | null;
  hit_rate_11: number | null;
  hit_rate_12: number | null;
  roi: number | null;
}

// ── /v1/signals ───────────────────────────────────────────────────────────────

export interface MatchSignal {
  match_number: number;
  home_team: string;
  away_team: string;
  fixture_id: string | null;
  league_name: string | null;
  kickoff_utc: string | null;
  recommended_pick: string;
  model_prob: number;
  pub_prob: number | null;
  edge_pp: number | null;
  crowd_disagreement_score: number | null;
  value_index: number | null;
  signal_strength: number;
  has_public_tips: boolean;
  prob_h: number;
  prob_u: number;
  prob_b: number;
  pub_prob_h: number | null;
  pub_prob_u: number | null;
  pub_prob_b: number | null;
  stats_signals: string[];
  classification: string;
  home_logo_url: string | null;
  away_logo_url: string | null;
}

export interface SignalBoardResponse {
  coupon_id: string;
  coupon_label: string;
  deadline_utc: string;
  week: number;
  year: number;
  signals: MatchSignal[];
}

// ── /v1/insights ─────────────────────────────────────────────────────────────

export interface OddsMovement {
  open_h: number;
  open_u: number;
  open_b: number;
  current_h: number;
  current_u: number;
  current_b: number;
  n_snapshots: number;
  direction: "steaming" | "drifting" | "stable";
  bookmaker: string;
}

export interface InsightSignal {
  match_number: number;
  home_team: string;
  away_team: string;
  fixture_id: string | null;
  league_name: string | null;
  kickoff_utc: string | null;
  recommended_pick: string;
  prob_h: number;
  prob_u: number;
  prob_b: number;
  model_prob: number;

  // NT public percentages — coupon layer only, never used for betting edge
  pub_prob_h: number | null;
  pub_prob_u: number | null;
  pub_prob_b: number | null;
  pub_prob: number | null;
  has_public_tips: boolean;
  edge_pp: number | null;               // model − pub in pp (coupon layer only)
  crowd_disagreement_score: number | null;
  value_index: number | null;

  // 1X2 bookmaker odds and market edge (betting value)
  odds_h: number | null;
  odds_u: number | null;
  odds_b: number | null;
  odds_source: string | null;
  implied_prob: number | null;          // de-vigged bookmaker implied prob (0–100)
  market_edge_pp: number | null;        // model_prob − implied_prob in pp

  odds_movement: OddsMovement | null;

  // Poisson: BTTS
  btts_model_prob: number | null;
  btts_yes_odds: number | null;
  btts_no_odds: number | null;
  btts_bookmaker: string | null;
  btts_implied_yes: number | null;
  btts_market_edge_pp: number | null;

  // Poisson: Over/Under 2.5
  over_model_prob: number | null;
  under_model_prob: number | null;
  over_25_odds: number | null;
  under_25_odds: number | null;
  ou_bookmaker: string | null;
  over_implied: number | null;
  over_market_edge_pp: number | null;

  // Poisson inputs
  xg_home: number | null;
  xg_away: number | null;

  // API-Football prediction signals
  af_winner_name:   string | null;
  af_winner_pick:   "H" | "U" | "B" | null;
  af_winner_agrees: boolean | null;
  af_win_or_draw:   boolean | null;
  af_under_over:    number | null;   // positive=Over, negative=Under
  af_advice:        string | null;
  af_poisson_home:  number | null;   // comparison.poisson_distribution.home (%)
  af_poisson_away:  number | null;
  af_goals_home:    number | null;
  af_goals_away:    number | null;
  af_ou_agrees:     boolean | null;

  // Composite confidence score (0–100)
  confidence_score: number | null;
}

export interface InsightsResponse {
  coupon_id: string;
  coupon_label: string;
  deadline_utc: string;
  week: number;
  year: number;
  signals: InsightSignal[];
}

export interface PaperBet {
  id: string;
  coupon_id: string | null;
  fixture_id: string;
  match_name: string;
  league: string | null;
  kickoff_utc: string | null;
  market: string;
  outcome: string;
  bookmaker: string;
  ref_odds: number;
  implied_prob: number;
  model_prob: number;
  edge_pp: number;
  stake_nok: number;
  expected_value: number;
  insight_type: string | null;
  risk_level: "low" | "medium" | "high";
  reason: string | null;
  model_quality: "full_model" | "partial_model" | "af_supported" | "generic_prior" | null;
  status: "pending" | "won" | "lost" | "void";
  result_outcome: string | null;
  closing_odds: number | null;
  clv: number | null;
  profit_nok: number | null;
  created_at: string;
  settled_at: string | null;
}

export interface BankrollPoint {
  bet_index: number;
  bankroll_after: number;
  label: string;
  market: string | null;
  outcome: string | null;
  profit_nok: number | null;
  odds: number | null;
  settled_at: string | null;
}

export interface BetSummary {
  starting_bankroll: number;
  current_bankroll: number;
  total_staked: number;
  total_profit: number;
  roi: number | null;
  n_won: number;
  n_lost: number;
  n_pending: number;
  hit_rate: number | null;
  avg_clv: number | null;
  by_market: Record<string, { n_won: number; n_lost: number; n_pending: number; profit: number; staked: number }>;
}

export interface GenerateBetsResponse {
  created: number;
  skipped: number;
  bets: PaperBet[];
}

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
  last_freeze_at: string | null;
  last_freeze_count: number;
  last_freeze_coupon_ids: string[];
}
