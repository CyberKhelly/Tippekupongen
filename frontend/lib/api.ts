import type {
  CdsValidationBucket,
  ConvictionStat,
  CouponListItem,
  GenerationAnalytics,
  GenerationDetail,
  GenerationSummary,
  HistoryCouponDetail,
  HistoryCouponItem,
  MatchEnrichment,
  NtComparison,
  OptimizeResponse,
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
