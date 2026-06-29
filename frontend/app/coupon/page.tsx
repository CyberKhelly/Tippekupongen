"use client";

import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { getCoupons, optimize, getSyncStatus, getEnrichment } from "@/lib/api";
import type { MatchEnrichment, Strategy } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { StrategySelector } from "@/components/StrategySelector";
import { BudgetInput } from "@/components/BudgetSelector";
import { MetricsRow } from "@/components/MetricsRow";
import { MatchTable } from "@/components/MatchTable";
import { cn, secsUntil } from "@/lib/utils";
import { Logo } from "@/components/brand/Logo";

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
    <header
      className="sticky top-0 z-20"
      style={{
        background: "var(--surf-0)",
        borderBottom: "1px solid var(--bdr-1)",
        height: 52,
        display: "flex",
        alignItems: "center",
      }}
    >
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 w-full flex items-center justify-between">
        {/* Wordmark */}
        <motion.div
          className="flex items-center gap-2.5"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <Logo size="sm" theme="dark" />
          <AnimatePresence>
            {weekLabel && (
              <motion.span
                initial={{ opacity: 0, scale: 0.88 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.88 }}
                transition={{ duration: 0.25 }}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  height: 20,
                  padding: "0 8px",
                  borderRadius: 4,
                  border: "1px solid rgba(255,255,255,0.08)",
                  background: "rgba(255,255,255,0.03)",
                  fontSize: 10,
                  fontWeight: 600,
                  color: "#4A4744",
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.04em",
                }}
              >
                {weekLabel}
              </motion.span>
            )}
          </AnimatePresence>
        </motion.div>

        {/* Connection status */}
        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            {isConnected && (
              <span
                className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
                style={{ background: "#22C55E" }}
              />
            )}
            <span
              className="relative inline-flex rounded-full h-1.5 w-1.5"
              style={{ background: isConnected ? "#22C55E" : "#F05252" }}
            />
          </span>
          <span
            className="hidden sm:block"
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              fontWeight: 500,
              color: "#3A3735",
            }}
          >
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
    <div
      className="sticky top-[52px] z-10"
      style={{ background: "var(--surf-0)", borderBottom: "1px solid var(--bdr-0)" }}
    >
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6">
        <div className="flex items-center h-12 gap-0">
          {/* Strategy */}
          <div
            className="flex items-center gap-4 pr-5 h-full"
            style={{ borderRight: "1px solid rgba(255,255,255,0.06)" }}
          >
            <span
              className="hidden sm:block shrink-0"
              style={{
                fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                color: "#2E2C2A", textTransform: "uppercase", letterSpacing: "0.12em",
              }}
            >
              Strategi
            </span>
            <StrategySelector variant="horizontal" selected={strategy} onSelect={onStrategy} />
          </div>

          {/* Budget */}
          <div className="flex items-center gap-3 pl-5 h-full">
            <span
              className="hidden sm:block shrink-0"
              style={{
                fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                color: "#2E2C2A", textTransform: "uppercase", letterSpacing: "0.12em",
              }}
            >
              Budsjett
            </span>
            <BudgetInput value={budget} onChange={onBudget} />
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
    <div
      className="px-5 py-2.5 flex items-center gap-5"
      style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }}
    >
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          fontWeight: 600,
          color: "#2E2C2A",
          textTransform: "uppercase",
          letterSpacing: "0.12em",
        }}
      >
        Form
      </span>
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              fontWeight: 700,
              color: "#E8E4DD",
              lineHeight: 1,
            }}
          >
            {n_singles}
          </span>
          <span style={{ fontSize: 10, color: "#4A4744" }}>singel</span>
        </div>
        <span style={{ color: "rgba(255,255,255,0.07)", fontSize: 12 }}>·</span>
        <div className="flex items-center gap-1.5">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              fontWeight: 700,
              color: n_halvdekk > 0 ? "#7A7673" : "#2E2C2A",
              lineHeight: 1,
            }}
          >
            {n_halvdekk}
          </span>
          <span style={{ fontSize: 10, color: n_halvdekk > 0 ? "#4A4744" : "#2E2C2A" }}>halvdekk</span>
        </div>
        <span style={{ color: "rgba(255,255,255,0.07)", fontSize: 12 }}>·</span>
        <div className="flex items-center gap-1.5">
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 13,
              fontWeight: 700,
              color: n_heldekk > 0 ? "#22C55E" : "#2E2C2A",
              lineHeight: 1,
            }}
          >
            {n_heldekk}
          </span>
          <span style={{ fontSize: 10, color: n_heldekk > 0 ? "#4A4744" : "#2E2C2A" }}>heldekk</span>
        </div>
      </div>
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
    <div className="pl-12 min-h-screen" style={{ background: "var(--canvas)" }}>
      <TopBar isConnected={isConnected} weekLabel={weekLabel} />
      <ControlsStrip strategy={strategy} onStrategy={setStrategy} budget={budget} onBudget={setBudget} />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-5 sm:py-6">
        {/* Offline banner */}
        <AnimatePresence>
          {isApiOffline && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-5 p-3.5 rounded-xl border border-[#F05252]/20 bg-[#F05252]/[0.06] text-sm text-[#F05252] flex items-start gap-3"
            >
              <span className="mt-0.5 shrink-0">⚠</span>
              <div>
                Backend kjører ikke.{" "}
                <code className="text-[11px] font-mono bg-[#F05252]/[0.1] px-1 rounded">
                  .\start-dev.ps1
                </code>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coupon tabs */}
        <motion.div
          className="mb-5"
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

        {/* Metrics strip */}
        <div className="mb-4">
          <MetricsRow result={result} isLoading={isLoading} />
        </div>

        {/* Match table */}
        <MatchTable
          matches={result?.matches ?? []}
          enrichmentMap={enrichmentMap}
          isLoading={isLoading || !selectedCouponId}
          grouped
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
