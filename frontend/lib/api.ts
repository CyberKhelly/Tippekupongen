import type {
  BankrollPoint,
  BetSummary,
  CdsValidationBucket,
  ConvictionStat,
  CouponDetail,
  CouponListItem,
  GenerateBetsResponse,
  GenerationAnalytics,
  GenerationDetail,
  GenerationSummary,
  HistoryCouponDetail,
  HistoryCouponItem,
  InsightsResponse,
  MatchEnrichment,
  NtComparison,
  OptimizeResponse,
  PaperBet,
  SignalBoardResponse,
  StrategyPerformance,
  Strategy,
  SyncStatus,
} from "./types";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function getCoupons(
  week?: number,
  year?: number
): Promise<CouponListItem[]> {
  const params = new URLSearchParams();
  if (week != null) params.set("week", String(week));
  if (year != null) params.set("year", String(year));
  const qs = params.toString() ? `?${params}` : "";
  return apiFetch<CouponListItem[]>(`/v1/coupons${qs}`);
}

export async function getHealth(): Promise<{ status: string; timestamp: string }> {
  return apiFetch("/health");
}

export interface OptimizeRequest {
  coupon_id: string;
  strategy: Strategy;
  budget: number;
  cost_per_row?: number;
  omsetning?: number;
}

export async function optimize(req: OptimizeRequest): Promise<OptimizeResponse> {
  return apiFetch<OptimizeResponse>("/v1/optimize", {
    method: "POST",
    body: JSON.stringify({ cost_per_row: 1.0, ...req }),
  });
}

export async function getSyncStatus(): Promise<SyncStatus> {
  return apiFetch<SyncStatus>("/v1/sync/status");
}

export async function triggerRefreshCoupons(): Promise<{ accepted: boolean; message: string }> {
  return apiFetch("/v1/sync/refresh-coupons", { method: "POST" });
}

export async function triggerDailySync(): Promise<{ accepted: boolean; message: string }> {
  return apiFetch("/v1/sync/daily", { method: "POST" });
}

// ── History ───────────────────────────────────────────────────────────────────

export async function getHistory(): Promise<HistoryCouponItem[]> {
  return apiFetch<HistoryCouponItem[]>("/v1/history");
}

export async function getHistoryCoupon(couponId: string): Promise<HistoryCouponDetail> {
  return apiFetch<HistoryCouponDetail>(`/v1/history/${couponId}`);
}

export async function getHistoryStrategyPerformance(): Promise<StrategyPerformance[]> {
  return apiFetch<StrategyPerformance[]>("/v1/history/strategy-performance");
}

export async function getHistoryCdsValidation(): Promise<CdsValidationBucket[]> {
  return apiFetch<CdsValidationBucket[]>("/v1/history/cds-validation");
}

export async function getHistoryConvictionStats(): Promise<ConvictionStat[]> {
  return apiFetch<ConvictionStat[]>("/v1/history/conviction-stats");
}

export async function getHistoryNtComparison(): Promise<NtComparison | null> {
  return apiFetch<NtComparison | null>("/v1/history/nt-comparison");
}

// ── Coupon detail (raw fixtures + kickoff times) ──────────────────────────────

export async function getCouponDetail(couponId: string): Promise<CouponDetail> {
  return apiFetch<CouponDetail>(`/v1/coupons/${couponId}`);
}

// ── Enrichment ────────────────────────────────────────────────────────────────

export async function getEnrichment(couponId: string): Promise<MatchEnrichment[]> {
  return apiFetch<MatchEnrichment[]>(`/v1/coupons/${couponId}/enrichment`);
}

// ── Phase 9 analytics ─────────────────────────────────────────────────────────

export async function getStrategyAnalytics(): Promise<GenerationAnalytics[]> {
  return apiFetch<GenerationAnalytics[]>("/v1/analytics/strategy");
}

export async function getGenerations(): Promise<GenerationSummary[]> {
  return apiFetch<GenerationSummary[]>("/v1/analytics/generations");
}

export async function getGenerationDetail(generationId: string): Promise<GenerationDetail> {
  return apiFetch<GenerationDetail>(`/v1/analytics/generations/${generationId}`);
}

// ── Signal board ──────────────────────────────────────────────────────────────

export async function getSignalBoard(couponId?: string): Promise<SignalBoardResponse> {
  const qs = couponId ? `?coupon_id=${encodeURIComponent(couponId)}` : "";
  return apiFetch<SignalBoardResponse>(`/v1/signals${qs}`);
}

// ── Oddstips insights ─────────────────────────────────────────────────────────

export async function getInsights(couponId?: string): Promise<InsightsResponse> {
  const qs = couponId ? `?coupon_id=${encodeURIComponent(couponId)}` : "";
  return apiFetch<InsightsResponse>(`/v1/insights${qs}`);
}

// ── Modellspill (paper bets) ───────────────────────────────────────────────────

export async function getBets(params?: { status?: string; market?: string }): Promise<PaperBet[]> {
  const qs = new URLSearchParams();
  if (params?.status) qs.set("status", params.status);
  if (params?.market) qs.set("market", params.market);
  const q = qs.toString();
  return apiFetch<PaperBet[]>(`/v1/bets${q ? `?${q}` : ""}`);
}

export async function getBetSummary(): Promise<BetSummary> {
  return apiFetch<BetSummary>("/v1/bets/summary");
}

export async function getBankroll(): Promise<BankrollPoint[]> {
  return apiFetch<BankrollPoint[]>("/v1/bets/bankroll");
}

export async function generateBets(couponId?: string): Promise<GenerateBetsResponse> {
  const qs = couponId ? `?coupon_id=${encodeURIComponent(couponId)}` : "";
  return apiFetch<GenerateBetsResponse>(`/v1/bets/generate${qs}`, { method: "POST" });
}

export async function settleBets(fixtureId: string): Promise<{ settled: number }> {
  return apiFetch<{ settled: number }>(`/v1/bets/settle/${encodeURIComponent(fixtureId)}`, { method: "POST" });
}

export interface ScanResponse {
  scan: {
    n_leagues: number;
    n_fixtures_found: number;
    n_fixtures_new: number;
    n_1x2_stored: number;
    n_markets_stored: number;
    n_no_odds: number;
    n_errors: number;
    n_api_calls: number;
  };
  candidates: {
    n_evaluated: number;
    n_created: number;
    n_skipped: number;
    min_edge_pp: number;
    tiers: { a: number; b: number; c: number };
    rejection_breakdown: {
      bad_odds: number;
      no_enr_1x2: number;
      edge_too_small: number;
      duplicate: number;
      error: number;
    };
  };
  duration_s: number;
}

export async function scanAndGenerateBets(lookaheadHours = 72): Promise<ScanResponse> {
  return apiFetch<ScanResponse>(`/v1/bets/scan?lookahead_hours=${lookaheadHours}`, { method: "POST" });
}
