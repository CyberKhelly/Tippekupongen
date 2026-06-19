"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { getCoupons, optimize, getSyncStatus } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { StrategySelector } from "@/components/StrategySelector";
import { BudgetSelector } from "@/components/BudgetSelector";
import { MetricsRow } from "@/components/MetricsRow";
import { MatchTable } from "@/components/MatchTable";
import { SyncStatusPanel } from "@/components/SyncStatus";
import { cn, secsUntil } from "@/lib/utils";

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
    <header className="sticky top-0 z-20 border-b border-white/[0.05]">
      <div className="absolute inset-0 bg-[#07101b]/85 backdrop-blur-md" />
      <div className="absolute bottom-0 inset-x-0 h-[1px] bg-gradient-to-r from-transparent via-amber-400/[0.18] to-transparent" />

      <div className="relative max-w-screen-xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="text-[17px] font-black tracking-tight select-none">
            <span className="text-slate-100">Tippe</span>
            <span className="text-amber-400">Q</span>
            <span className="text-slate-100">pongen</span>
          </span>
          <AnimatePresence>
            {weekLabel && (
              <motion.span
                initial={{ opacity: 0, scale: 0.88 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.88 }}
                transition={{ duration: 0.25 }}
                className="hidden sm:inline-flex items-center h-5 px-2 rounded-md border border-white/[0.07] bg-white/[0.04] text-[10px] font-semibold text-slate-500 tracking-wide"
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
          <span className="text-[11px] text-slate-600 font-medium hidden sm:block">
            {isConnected ? "API tilkoblet" : "Frakoblet"}
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
    { label: "Singler",  value: n_singles,  desc: "1 utfall", color: "bg-slate-500/70" },
    { label: "Halvdekk", value: n_halvdekk, desc: "2 utfall", color: "bg-amber-600/60" },
    { label: "Heldekk",  value: n_heldekk,  desc: "3 utfall", color: "bg-amber-400/80" },
  ] as const;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="relative glass rounded-xl p-4 overflow-hidden card-top-line"
    >
      <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-4">
        Kupongens form
      </p>
      <div className="space-y-3">
        {rows.map(({ label, value, desc, color }, i) => {
          const pct = total > 0 ? (value / total) * 100 : 0;
          return (
            <div key={label}>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs font-medium text-slate-300">{label}</span>
                  <span className="text-[10px] text-slate-600">{desc}</span>
                </div>
                <motion.span
                  key={value}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="text-sm font-bold tabular-nums text-slate-200"
                >
                  {value}
                </motion.span>
              </div>
              <div className="h-[2px] bg-slate-800 rounded-full overflow-hidden">
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
      <div className="mt-4 pt-3 border-t border-white/[0.05] flex items-center justify-between">
        <span className="text-[10px] text-slate-600">Total kamper</span>
        <span className="text-xs font-bold tabular-nums text-slate-500">{total}</span>
      </div>
    </motion.div>
  );
}

// ── Conviction legend ─────────────────────────────────────────────────────────

function ConvictionLegend({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex items-center gap-2.5 text-[11px] text-slate-500 px-1"
    >
      <span className="relative flex h-1.5 w-1.5 shrink-0">
        <span className="absolute inset-0 rounded-full bg-amber-400 animate-ping opacity-40" />
        <span className="relative rounded-full h-1.5 w-1.5 bg-amber-400" />
      </span>
      <span>
        <span className="text-amber-400 font-semibold">{count}</span>{" "}
        overbevisning{count !== 1 ? "er" : ""} — modellen avviker ≥10pp fra folket
      </span>
    </motion.div>
  );
}

// ── Section label ─────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-3">
      {children}
    </p>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function CouponPage() {
  const [selectedCouponId, setSelectedCouponId] = useState<string | null>(null);
  const [strategy, setStrategy] = useState<Strategy>("balanced");
  const [budget, setBudget] = useState<number>(192);
  const queryClient = useQueryClient();
  const prevNtRefreshRef = useRef<string | null>(null);

  const couponsQuery = useQuery({
    queryKey: ["coupons"],
    queryFn: () => getCoupons(),
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    if (couponsQuery.data?.length && !selectedCouponId) {
      setSelectedCouponId(couponsQuery.data[0].coupon_id);
    }
  }, [couponsQuery.data, selectedCouponId]);

  const currentCoupon = couponsQuery.data?.find((c) => c.coupon_id === selectedCouponId);
  const deadlineSecs = secsUntil(currentCoupon?.deadline_utc);

  // State-driven refetch interval — avoids TQ v5 callback API ambiguity
  const [syncRefetchMs, setSyncRefetchMs] = useState<number | false>(120_000);

  // Sync status — deadline-aware polling
  const syncQuery = useQuery({
    queryKey: ["sync-status"],
    queryFn: () => getSyncStatus(),
    staleTime: 0,
    refetchInterval: syncRefetchMs,
  });

  useEffect(() => {
    const isRunning = syncQuery.data?.is_running ?? false;
    const secs = isFinite(deadlineSecs) ? deadlineSecs : Infinity;
    setSyncRefetchMs(syncRefetchInterval(isRunning, secs));
  }, [syncQuery.data?.is_running, deadlineSecs]);

  // Invalidate optimize when a new NT refresh completes
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
    enabled: !!selectedCouponId,
    staleTime: 60_000,
    refetchInterval: isFinite(deadlineSecs)
      ? optimizeRefetchInterval(deadlineSecs)
      : false,
  });

  const result = optimizeQuery.data;
  const isLoading = optimizeQuery.isLoading || optimizeQuery.isFetching;
  const convictionCount = result?.matches.filter((m) => m.is_conviction).length ?? 0;
  const isConnected = !couponsQuery.isError && !optimizeQuery.isError;
  const weekLabel = currentCoupon
    ? `Uke ${currentCoupon.week} · ${currentCoupon.year}`
    : undefined;

  return (
    <div
      className="min-h-screen"
      style={{
        background:
          "radial-gradient(ellipse at 20% 0%, rgba(15,45,110,0.5) 0%, transparent 50%), radial-gradient(ellipse at 82% 90%, rgba(8,22,60,0.3) 0%, transparent 48%), #07101b",
      }}
    >
      {/* Dot grid texture */}
      <div
        className="fixed inset-0 pointer-events-none z-[-1]"
        style={{
          backgroundImage:
            "radial-gradient(circle at 1px 1px, rgba(148,163,184,0.035) 1px, transparent 0)",
          backgroundSize: "28px 28px",
        }}
      />

      <TopBar isConnected={isConnected} weekLabel={weekLabel} />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Error state */}
        <AnimatePresence>
          {(couponsQuery.isError || optimizeQuery.isError) && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-6 p-4 rounded-xl border border-red-500/20 bg-red-500/[0.04] text-sm text-red-400 flex items-start gap-3"
            >
              <span className="text-red-500 mt-0.5 shrink-0">⚠</span>
              <div>
                Klarte ikke å nå API-et.{" "}
                <span className="text-red-500/70">
                  Sjekk at FastAPI kjører på port 8000.
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coupon selector */}
        <motion.div
          className="mb-6 sm:mb-8"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <SectionLabel>Kupong</SectionLabel>
          <CouponSelector
            coupons={couponsQuery.data ?? []}
            selected={selectedCouponId}
            onSelect={setSelectedCouponId}
            isLoading={couponsQuery.isLoading}
          />
        </motion.div>

        {/* Two-column layout */}
        <div className="flex flex-col lg:grid lg:grid-cols-[1fr_272px] gap-5 lg:gap-6">

          {/* ── Main column ──────────────────────────────────────────────── */}
          <div className="min-w-0 space-y-4 sm:space-y-5">
            <MetricsRow result={result} isLoading={isLoading} />
            <AnimatePresence>
              {result && !isLoading && <ConvictionLegend count={convictionCount} />}
            </AnimatePresence>
            <MatchTable
              matches={result?.matches ?? []}
              isLoading={isLoading || !selectedCouponId}
            />
          </div>

          {/* ── Sidebar ──────────────────────────────────────────────────── */}
          <motion.div
            className="space-y-4 lg:sticky lg:top-[57px] lg:self-start"
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          >
            <div>
              <SectionLabel>Strategi</SectionLabel>
              <StrategySelector selected={strategy} onSelect={setStrategy} />
            </div>
            <div>
              <SectionLabel>Budsjett</SectionLabel>
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

            {/* Sync status panel */}
            <SyncStatusPanel
              status={syncQuery.data}
              isLoading={syncQuery.isLoading}
            />
          </motion.div>
        </div>
      </main>
    </div>
  );
}
