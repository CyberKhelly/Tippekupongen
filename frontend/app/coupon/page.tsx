"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { getCoupons, optimize, getSyncStatus, getEnrichment } from "@/lib/api";
import type { MatchEnrichment, Strategy } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { StrategySelector } from "@/components/StrategySelector";
import { BudgetSelector } from "@/components/BudgetSelector";
import { MetricsRow } from "@/components/MetricsRow";
import { MatchTable } from "@/components/MatchTable";
import { LogoMark } from "@/components/LogoMark";
import { cn, secsUntil } from "@/lib/utils";

const BUDGETS = [32, 96, 192, 384] as const;

// ── Polling intervals ─────────────────────────────────────────────────────────

function syncRefetchInterval(isRunning: boolean, deadlineSecs: number): number {
  if (isRunning) return 5_000;
  if (deadlineSecs < 30 * 60) return 30_000;
  if (deadlineSecs < 3 * 60 * 60) return 60_000;
  return 120_000;
}

function optimizeRefetchInterval(deadlineSecs: number): number {
  if (deadlineSecs < 30 * 60) return 60_000;
  if (deadlineSecs < 3 * 60 * 60) return 3 * 60_000;
  return 5 * 60_000;
}

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({ isConnected, weekLabel }: { isConnected: boolean; weekLabel?: string }) {
  return (
    <header className="sticky top-0 z-20 bg-white border-b border-[#E4E1DA]">
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 flex items-center justify-between" style={{ height: 52 }}>
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <LogoMark size={32} />
          <span className="text-[17px] font-black tracking-tight select-none">
            <span className="text-[#111110]">Tippe</span>
            <span className="text-[#D4930A]">Q</span>
            <span className="text-[#111110]">pongen</span>
          </span>
          <AnimatePresence>
            {weekLabel && (
              <motion.span
                initial={{ opacity: 0, scale: 0.88 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.88 }}
                transition={{ duration: 0.25 }}
                className="hidden sm:inline-flex items-center h-5 px-2 rounded border border-[#E4E1DA] bg-[#FAF9F7] text-[10px] font-semibold text-[#ADA9A2] tracking-wide"
              >
                {weekLabel}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.div>

        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="relative flex h-2 w-2">
            <span className={cn(
              "absolute inline-flex h-full w-full rounded-full opacity-60",
              isConnected ? "bg-[#15803D] animate-ping" : "bg-[#C42B2B]",
            )} />
            <span className={cn(
              "relative inline-flex rounded-full h-2 w-2",
              isConnected ? "bg-[#15803D]" : "bg-[#C42B2B]",
            )} />
          </span>
          <span className="text-[11px] text-[#ADA9A2] font-medium hidden sm:block">
            {isConnected ? "tilkoblet" : "frakoblet"}
          </span>
        </motion.div>
      </div>
    </header>
  );
}

// ── Controls strip ────────────────────────────────────────────────────────────

function ControlsStrip({
  strategy, onStrategy, budget, onBudget,
}: {
  strategy: Strategy; onStrategy: (s: Strategy) => void;
  budget: number;    onBudget:   (b: number) => void;
}) {
  return (
    <div className="sticky top-[52px] z-10 bg-[#FAF9F7] border-b border-[#E4E1DA]">
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 py-3">
        <div className="flex flex-col sm:flex-row gap-2.5 sm:items-center sm:gap-8">
          <div className="flex items-center gap-3 flex-1 min-w-0">
            <span className="text-[9px] font-semibold text-[#ADA9A2] uppercase tracking-widest shrink-0 hidden sm:block">
              Strategi
            </span>
            <div className="flex-1 min-w-0">
              <StrategySelector variant="horizontal" selected={strategy} onSelect={onStrategy} />
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-[9px] font-semibold text-[#ADA9A2] uppercase tracking-widest shrink-0 hidden sm:block">
              Budsjett
            </span>
            <BudgetSelector variant="horizontal" budgets={[...BUDGETS]} selected={budget} onSelect={onBudget} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Shape strip ───────────────────────────────────────────────────────────────

function ShapeStrip({ n_singles, n_halvdekk, n_heldekk }: {
  n_singles: number; n_halvdekk: number; n_heldekk: number;
}) {
  return (
    <div className="px-4 py-2.5 text-[11px] text-[#6B6862]">
      <span className="text-[9px] text-[#ADA9A2] uppercase tracking-widest font-semibold mr-3">Form</span>
      <span className="font-semibold text-[#111110]">{n_singles}</span> Singel
      <span className="text-[#C8C4BC] mx-2">·</span>
      <span className={cn("font-semibold", n_halvdekk > 0 ? "text-[#6B6862]" : "text-[#ADA9A2]")}>{n_halvdekk}</span> Halvdekk
      <span className="text-[#C8C4BC] mx-2">·</span>
      <span className={cn("font-semibold", n_heldekk > 0 ? "text-[#15803D]" : "text-[#ADA9A2]")}>{n_heldekk}</span> Heldekk
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CouponPage() {
  const [selectedCouponId, setSelectedCouponId] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<Strategy>("balanced");
  const [budget, setBudget] = useState<number>(192);
  const queryClient = useQueryClient();
  const prevNtRefreshRef = useRef<string | null>(null);

  const [couponsRefetchMs, setCouponsRefetchMs] = useState<number | false>(false);

  const couponsQuery = useQuery({
    queryKey: ["coupons"],
    queryFn: () => getCoupons(),
    staleTime: 5 * 60_000,
    retry: 1,
    refetchInterval: couponsRefetchMs,
  });

  useEffect(() => {
    setCouponsRefetchMs(couponsQuery.isError ? 30_000 : false);
  }, [couponsQuery.isError]);

  useEffect(() => {
    if (couponsQuery.data?.length && !selectedCouponId) {
      setSelectedCouponId(couponsQuery.data[0].coupon_id);
    }
  }, [couponsQuery.data, selectedCouponId]);

  const currentCoupon = couponsQuery.data?.find((c) => c.coupon_id === selectedCouponId);
  const deadlineSecs  = secsUntil(currentCoupon?.deadline_utc);
  const isApiOffline  = couponsQuery.isError;

  const [syncRefetchMs, setSyncRefetchMs] = useState<number | false>(120_000);

  const syncQuery = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => getSyncStatus(),
    staleTime: 0,
    retry: 1,
    refetchInterval: syncRefetchMs,
  });

  useEffect(() => {
    if (isApiOffline) { setSyncRefetchMs(30_000); return; }
    const isRunning = syncQuery.data?.is_running ?? false;
    const secs = isFinite(deadlineSecs) ? deadlineSecs : Infinity;
    setSyncRefetchMs(syncRefetchInterval(isRunning, secs));
  }, [isApiOffline, syncQuery.data?.is_running, deadlineSecs]);

  useEffect(() => {
    const latestNt = syncQuery.data?.last_nt_refresh_at ?? null;
    if (latestNt && latestNt !== prevNtRefreshRef.current) {
      if (prevNtRefreshRef.current !== null) queryClient.invalidateQueries({ queryKey: ["optimize"] });
      prevNtRefreshRef.current = latestNt;
    }
  }, [syncQuery.data?.last_nt_refresh_at, queryClient]);

  const optimizeQuery = useQuery({
    queryKey: ["optimize", selectedCouponId, strategy, budget],
    queryFn: () => optimize({ coupon_id: selectedCouponId!, strategy, budget, cost_per_row: 1.0 }),
    enabled: !!selectedCouponId && !isApiOffline,
    staleTime: 60_000,
    retry: 1,
    refetchInterval: isFinite(deadlineSecs) ? optimizeRefetchInterval(deadlineSecs) : false,
  });

  const enrichmentQuery = useQuery({
    queryKey: ["enrichment", selectedCouponId],
    queryFn: () => getEnrichment(selectedCouponId!),
    enabled: !!selectedCouponId && !isApiOffline,
    staleTime: 10 * 60_000,
    retry: 1,
  });

  const enrichmentMap = new Map<number, MatchEnrichment>(
    (enrichmentQuery.data ?? []).map((e) => [e.match_number, e])
  );

  const result    = optimizeQuery.data;
  const isLoading = optimizeQuery.isLoading || optimizeQuery.isFetching;
  const isConnected = !isApiOffline;
  const weekLabel = currentCoupon
    ? `Uke ${currentCoupon.week} · ${currentCoupon.year}`
    : undefined;

  return (
    <div className="relative min-h-screen bg-[#F5F3EF]">
      <TopBar isConnected={isConnected} weekLabel={weekLabel} />
      <ControlsStrip strategy={strategy} onStrategy={setStrategy} budget={budget} onBudget={setBudget} />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Offline banner */}
        <AnimatePresence>
          {isApiOffline && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-5 p-3.5 rounded-xl border border-[#C42B2B]/20 bg-[#C42B2B]/[0.04] text-sm text-[#C42B2B] flex items-start gap-3"
            >
              <span className="mt-0.5 shrink-0">⚠</span>
              <div>
                Backend kjører ikke.{" "}
                <code className="text-[11px] font-mono bg-[#C42B2B]/[0.08] px-1 rounded">
                  .\start-dev.ps1
                </code>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coupon tabs */}
        <motion.div
          className="mb-6 sm:mb-8"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <CouponSelector
            coupons={couponsQuery.data ?? []}
            selected={selectedCouponId}
            onSelect={setSelectedCouponId}
            isLoading={couponsQuery.isLoading}
          />
        </motion.div>

        {/* Metrics */}
        <div className="mb-4">
          <MetricsRow result={result} isLoading={isLoading} />
        </div>

        {/* Match table */}
        <MatchTable
          matches={result?.matches ?? []}
          enrichmentMap={enrichmentMap}
          isLoading={isLoading || !selectedCouponId}
          footer={
            result ? (
              <ShapeStrip
                n_singles={result.shape.n_singles}
                n_halvdekk={result.shape.n_halvdekk}
                n_heldekk={result.shape.n_heldekk}
              />
            ) : undefined
          }
        />
      </main>
    </div>
  );
}
