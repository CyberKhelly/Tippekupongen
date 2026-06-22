"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import { getCoupons, optimize, getSyncStatus, getEnrichment } from "@/lib/api";
import type { MatchEnrichment, Strategy } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { StrategySelector } from "@/components/StrategySelector";
import { BudgetSelector } from "@/components/BudgetSelector";
import { MetricsRow } from "@/components/MetricsRow";
import { MatchTable } from "@/components/MatchTable";
import { cn, secsUntil } from "@/lib/utils";
import { LogoMark } from "@/components/LogoMark";

const BUDGETS = [32, 96, 192, 384] as const;

// ── Deadline-aware polling intervals ─────────────────────────────────────────

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

// ── Top navigation ────────────────────────────────────────────────────────────

function TopBar({
  isConnected,
  weekLabel,
}: {
  isConnected: boolean;
  weekLabel?: string;
}) {
  return (
    <header className="sticky top-0 z-20 border-b border-[#202020]">
      <div className="absolute inset-0 bg-[#050505]/95 backdrop-blur-md" />

      <div className="relative max-w-screen-xl mx-auto px-4 sm:px-6 flex items-center justify-between" style={{ height: 52 }}>
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <div className="rounded-xl border border-[#282828] overflow-hidden shrink-0">
            <LogoMark size={36} />
          </div>

          <span className="text-[17px] font-black tracking-tight select-none">
            <span className="text-zinc-100">Tippe</span>
            <span className="text-[#F5C542]">Q</span>
            <span className="text-zinc-100">pongen</span>
          </span>

          <AnimatePresence>
            {weekLabel && (
              <motion.span
                initial={{ opacity: 0, scale: 0.88 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.88 }}
                transition={{ duration: 0.25 }}
                className="hidden sm:inline-flex items-center h-5 px-2 rounded border border-[#202020] bg-[#111] text-[10px] font-semibold text-zinc-600 tracking-wide"
              >
                {weekLabel}
              </motion.span>
            )}
          </AnimatePresence>

          <Link
            href="/history"
            className="hidden sm:flex items-center h-7 px-3 rounded-md text-[11px] font-medium text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.04] transition-colors"
          >
            Historikk
          </Link>
        </motion.div>

        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="relative flex h-2 w-2">
            <span
              className={cn(
                "absolute inline-flex h-full w-full rounded-full opacity-60",
                isConnected ? "bg-emerald-400 animate-ping" : "bg-red-500"
              )}
            />
            <span
              className={cn(
                "relative inline-flex rounded-full h-2 w-2",
                isConnected ? "bg-emerald-400" : "bg-red-500"
              )}
            />
          </span>
          <span className="text-[11px] text-zinc-700 font-medium hidden sm:block">
            {isConnected ? "tilkoblet" : "frakoblet"}
          </span>
        </motion.div>
      </div>
    </header>
  );
}

// ── Shape panel ───────────────────────────────────────────────────────────────

function ShapePanel({
  n_singles,
  n_halvdekk,
  n_heldekk,
}: {
  n_singles: number;
  n_halvdekk: number;
  n_heldekk: number;
}) {
  const total = n_singles + n_halvdekk + n_heldekk;
  const rows = [
    { label: "Singler",  value: n_singles,  color: "bg-zinc-600/50" },
    { label: "Halvdekk", value: n_halvdekk, color: "bg-zinc-500/40" },
    { label: "Heldekk",  value: n_heldekk,  color: "bg-emerald-600/55" },
  ] as const;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="rounded-xl border border-[#202020] bg-[#101010] p-4"
    >
      <p className="font-display text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-3">
        Kupongens form
      </p>
      <div className="space-y-2.5">
        {rows.map(({ label, value, color }, i) => {
          const pct = total > 0 ? (value / total) * 100 : 0;
          return (
            <div key={label}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[11px] font-medium text-zinc-400">{label}</span>
                <motion.span
                  key={value}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-[11px] font-bold tabular-nums text-zinc-200"
                >
                  {value}
                </motion.span>
              </div>
              <div className="h-[2px] bg-[#1a1a1a] rounded-full overflow-hidden">
                <motion.div
                  className={cn("h-full rounded-full", color)}
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ delay: i * 0.08, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 pt-3 border-t border-[#1a1a1a] flex items-center justify-between">
        <span className="text-[9px] text-zinc-700">Total</span>
        <span className="text-[11px] font-bold tabular-nums text-zinc-600">{total}</span>
      </div>
    </motion.div>
  );
}

// ── Conviction legend ─────────────────────────────────────────────────────────

function ConvictionLegend({ count }: { count: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-center gap-2 text-[11px] px-1"
    >
      {count > 0 ? (
        <>
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            <span className="absolute inset-0 rounded-full bg-amber-400 animate-ping opacity-40" />
            <span className="relative rounded-full h-1.5 w-1.5 bg-amber-400" />
          </span>
          <span className="text-zinc-500">
            <span className="text-amber-400 font-semibold">{count}</span>{" "}
            overbevisning{count !== 1 ? "er" : ""} — modellen avviker ≥10pp fra folket
          </span>
        </>
      ) : (
        <>
          <span className="w-1.5 h-1.5 rounded-full bg-zinc-800 shrink-0" />
          <span className="text-zinc-700">Ingen overbevisninger — modellen og folket er i stor grad enige</span>
        </>
      )}
    </motion.div>
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
  const deadlineSecs = secsUntil(currentCoupon?.deadline_utc);
  const isApiOffline = couponsQuery.isError;

  const [syncRefetchMs, setSyncRefetchMs] = useState<number | false>(120_000);

  const syncQuery = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => getSyncStatus(),
    staleTime: 0,
    retry: 1,
    refetchInterval: syncRefetchMs,
  });

  useEffect(() => {
    if (isApiOffline) {
      setSyncRefetchMs(30_000);
      return;
    }
    const isRunning = syncQuery.data?.is_running ?? false;
    const secs = isFinite(deadlineSecs) ? deadlineSecs : Infinity;
    setSyncRefetchMs(syncRefetchInterval(isRunning, secs));
  }, [isApiOffline, syncQuery.data?.is_running, deadlineSecs]);

  useEffect(() => {
    const latestNt = syncQuery.data?.last_nt_refresh_at ?? null;
    if (latestNt && latestNt !== prevNtRefreshRef.current) {
      if (prevNtRefreshRef.current !== null) {
        queryClient.invalidateQueries({ queryKey: ["optimize"] });
      }
      prevNtRefreshRef.current = latestNt;
    }
  }, [syncQuery.data?.last_nt_refresh_at, queryClient]);

  const optimizeQuery = useQuery({
    queryKey: ["optimize", selectedCouponId, strategy, budget],
    queryFn: () =>
      optimize({ coupon_id: selectedCouponId!, strategy, budget, cost_per_row: 1.0 }),
    enabled: !!selectedCouponId && !isApiOffline,
    staleTime: 60_000,
    retry: 1,
    refetchInterval: isFinite(deadlineSecs)
      ? optimizeRefetchInterval(deadlineSecs)
      : false,
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

  const result = optimizeQuery.data;
  const isLoading = optimizeQuery.isLoading || optimizeQuery.isFetching;
  const convictionCount = result?.matches.filter((m) => m.is_conviction).length ?? 0;
  const isConnected = !isApiOffline;
  const weekLabel = currentCoupon
    ? `Uke ${currentCoupon.week} · ${currentCoupon.year}`
    : undefined;

  return (
    <div className="min-h-screen" style={{ background: "#050505" }}>
      <TopBar isConnected={isConnected} weekLabel={weekLabel} />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-5 sm:py-7">
        {/* Offline banner */}
        <AnimatePresence>
          {isApiOffline && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-5 p-3.5 rounded-xl border border-red-500/20 bg-red-500/[0.04] text-sm text-red-400 flex items-start gap-3"
            >
              <span className="mt-0.5 shrink-0">⚠</span>
              <div>
                Backend kjører ikke.{" "}
                <code className="text-[11px] font-mono bg-red-950/40 px-1 rounded">
                  .\start-dev.ps1
                </code>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coupon tabs */}
        <motion.div
          className="mb-5 sm:mb-6"
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

        {/* Two-column layout */}
        <div className="flex flex-col lg:grid lg:grid-cols-[1fr_264px] gap-5 lg:gap-6">

          {/* ── Main column ──────────────────────────────────────────────── */}
          <div className="min-w-0 space-y-4">
            <MetricsRow result={result} isLoading={isLoading} />
            <AnimatePresence>
              {result && !isLoading && <ConvictionLegend count={convictionCount} />}
            </AnimatePresence>
            <MatchTable
              matches={result?.matches ?? []}
              enrichmentMap={enrichmentMap}
              isLoading={isLoading || !selectedCouponId}
            />
          </div>

          {/* ── Sidebar ──────────────────────────────────────────────────── */}
          <motion.div
            className="space-y-4 lg:sticky lg:top-[52px] lg:self-start"
            initial={{ opacity: 0, x: 10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <div>
              <p className="font-display text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-2">Strategi</p>
              <StrategySelector selected={strategy} onSelect={setStrategy} />
            </div>
            <div>
              <p className="font-display text-xs font-semibold text-zinc-400 uppercase tracking-widest mb-2">Budsjett</p>
              <BudgetSelector
                budgets={[...BUDGETS]}
                selected={budget}
                onSelect={setBudget}
              />
            </div>
            <AnimatePresence mode="wait">
              {result && (
                <ShapePanel
                  key={`${result.strategy}-${result.budget}`}
                  n_singles={result.shape.n_singles}
                  n_halvdekk={result.shape.n_halvdekk}
                  n_heldekk={result.shape.n_heldekk}
                />
              )}
            </AnimatePresence>
          </motion.div>
        </div>
      </main>
    </div>
  );
}
