"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import {
  getCoupons, optimize, getSyncStatus, getEnrichment,
  saveCoupon, listSavedSnapshots, deleteSavedSnapshot,
} from "@/lib/api";
import type { MatchEnrichment, Strategy, SavedCouponSummary } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { StrategySelector } from "@/components/StrategySelector";
import { BudgetInput } from "@/components/BudgetSelector";
import { MetricsRow } from "@/components/MetricsRow";
import { MatchTable } from "@/components/MatchTable";
import { cn, secsUntil, formatRelative } from "@/lib/utils";
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

// ── Shape strip (with save button) ───────────────────────────────────────────

function ShapeStrip({
  n_singles, n_halvdekk, n_heldekk,
  onSave, isSaving, saveLabel,
}: {
  n_singles: number; n_halvdekk: number; n_heldekk: number;
  onSave?: () => void;
  isSaving?: boolean;
  saveLabel?: string;
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

      {/* Save button — right-aligned */}
      {onSave && (
        <button
          onClick={onSave}
          disabled={isSaving}
          style={{
            marginLeft: "auto",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            height: 26,
            padding: "0 10px",
            borderRadius: 5,
            border: `1px solid rgba(245,197,66,${isSaving ? "0.15" : "0.28"})`,
            background: "transparent",
            cursor: isSaving ? "default" : "pointer",
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            fontWeight: 600,
            color: isSaving ? "rgba(245,197,66,0.35)" : "rgba(245,197,66,0.7)",
            letterSpacing: "0.04em",
            transition: "border-color 0.15s, color 0.15s, background 0.15s",
          }}
          onMouseEnter={(e) => {
            if (!isSaving) {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(245,197,66,0.65)";
              (e.currentTarget as HTMLButtonElement).style.color = "#F5C542";
              (e.currentTarget as HTMLButtonElement).style.background = "rgba(245,197,66,0.04)";
            }
          }}
          onMouseLeave={(e) => {
            if (!isSaving) {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "rgba(245,197,66,0.28)";
              (e.currentTarget as HTMLButtonElement).style.color = "rgba(245,197,66,0.7)";
              (e.currentTarget as HTMLButtonElement).style.background = "transparent";
            }
          }}
        >
          {isSaving ? (
            <>
              <span
                style={{
                  display: "inline-block",
                  width: 8,
                  height: 8,
                  borderRadius: "50%",
                  border: "1.5px solid rgba(245,197,66,0.2)",
                  borderTopColor: "rgba(245,197,66,0.5)",
                  animation: "spin 0.7s linear infinite",
                }}
              />
              Lagrer...
            </>
          ) : (
            <>
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ opacity: 0.7 }}>
                <path
                  d="M1.5 1.5h5.5L8.5 3v5.5h-7V1.5zM3 1.5V4h4V1.5M3.5 6.5h3"
                  stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"
                />
              </svg>
              {saveLabel ?? "Lagre kupong"}
            </>
          )}
        </button>
      )}
    </div>
  );
}

// ── Saved snapshots section ───────────────────────────────────────────────────

const STRATEGY_COLORS: Record<string, string> = {
  balanced: "#7B92FF",
  jackpot:  "#F5C542",
  safe:     "#64748B",
};

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return (v * 100).toFixed(2) + "%";
}

function fmtNum(v: number | null | undefined, decimals = 1): string {
  if (v == null) return "—";
  return v.toFixed(decimals);
}

function SnapshotRow({
  snap,
  onDelete,
  isDeleting,
}: {
  snap: SavedCouponSummary;
  onDelete: (id: string) => void;
  isDeleting: boolean;
}) {
  const color = STRATEGY_COLORS[snap.strategy] ?? "#7A7673";
  const shapeLabel = `${snap.singles_count}S · ${snap.half_cover_count}H · ${snap.full_cover_count}F`;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: isDeleting ? 0.4 : 1, y: 0 }}
      exit={{ opacity: 0, height: 0, marginBottom: 0 }}
      transition={{ duration: 0.2 }}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        padding: "7px 14px",
        borderBottom: "1px solid rgba(255,255,255,0.035)",
      }}
    >
      {/* Strategy tag */}
      <span
        style={{
          minWidth: 72,
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          fontWeight: 700,
          color,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
        }}
      >
        {snap.strategy}
      </span>

      {/* Budget */}
      <span
        style={{
          width: 60,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          fontWeight: 600,
          color: "#8A8481",
        }}
      >
        {snap.budget_nok} kr
      </span>

      {/* Rows */}
      <span
        style={{
          width: 60,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "#6A6361",
        }}
      >
        {snap.total_rows}r
      </span>

      {/* P(12) */}
      <span
        style={{
          width: 64,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "#8A8481",
        }}
      >
        {fmtPct(snap.p_win)}
      </span>

      {/* PVR */}
      <span
        style={{
          width: 52,
          fontFamily: "var(--font-mono)",
          fontSize: 11,
          color: "#6A6361",
        }}
      >
        {fmtNum(snap.pvr)}x
      </span>

      {/* Shape */}
      <span
        style={{
          flex: 1,
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "#5A5755",
          letterSpacing: "0.04em",
        }}
      >
        {shapeLabel}
      </span>

      {/* Saved at */}
      <span
        style={{
          minWidth: 80,
          textAlign: "right",
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          color: "#4A4744",
        }}
      >
        {formatRelative(snap.saved_at)}
      </span>

      {/* Delete */}
      <button
        onClick={() => onDelete(snap.snapshot_id)}
        disabled={isDeleting}
        title="Slett snapshot"
        style={{
          marginLeft: 12,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: 22,
          height: 22,
          borderRadius: 4,
          border: "none",
          background: "transparent",
          cursor: isDeleting ? "default" : "pointer",
          color: "#3A3735",
          opacity: isDeleting ? 0.3 : 1,
          transition: "color 0.12s",
          padding: 0,
        }}
        onMouseEnter={(e) => {
          if (!isDeleting)
            (e.currentTarget as HTMLButtonElement).style.color = "#F05252";
        }}
        onMouseLeave={(e) => {
          if (!isDeleting)
            (e.currentTarget as HTMLButtonElement).style.color = "#3A3735";
        }}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path
            d="M2 3h8M4.5 3V2h3v1M5 5.5v3M7 5.5v3M3 3l.5 6.5h5L9 3"
            stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round"
          />
        </svg>
      </button>
    </motion.div>
  );
}

function SavedSnapshotsSection({
  couponId,
  snapshots,
  onDelete,
  deletingId,
}: {
  couponId: string | null;
  snapshots: SavedCouponSummary[];
  onDelete: (id: string) => void;
  deletingId: string | null;
}) {
  if (!couponId) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.1 }}
      style={{
        marginTop: 16,
        borderRadius: 10,
        border: "1px solid rgba(255,255,255,0.055)",
        background: "var(--surf-0)",
        overflow: "hidden",
      }}
    >
      {/* Section header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "9px 14px",
          borderBottom: "1px solid rgba(255,255,255,0.05)",
          background: "rgba(255,255,255,0.015)",
        }}
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
          Lagrede snapshots
        </span>
        {snapshots.length > 0 && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              height: 16,
              padding: "0 6px",
              borderRadius: 3,
              background: "rgba(255,255,255,0.04)",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              fontWeight: 600,
              color: "#4A4744",
            }}
          >
            {snapshots.length}
          </span>
        )}

        {/* Column headers */}
        {snapshots.length > 0 && (
          <div
            style={{
              marginLeft: "auto",
              display: "flex",
              alignItems: "center",
              gap: 0,
            }}
          >
            {[
              { label: "Strategi", w: 72 },
              { label: "Budsjett", w: 60 },
              { label: "Rader", w: 60 },
              { label: "P(12)", w: 64 },
              { label: "PVR", w: 52 },
              { label: "Form", w: undefined },
            ].map(({ label, w }) => (
              <span
                key={label}
                style={{
                  width: w,
                  flex: w ? undefined : 1,
                  fontFamily: "var(--font-mono)",
                  fontSize: 8,
                  fontWeight: 600,
                  color: "#2A2825",
                  textTransform: "uppercase",
                  letterSpacing: "0.10em",
                }}
              >
                {label}
              </span>
            ))}
            {/* spacers for timestamp + delete */}
            <span style={{ minWidth: 80 + 12 + 22 }} />
          </div>
        )}
      </div>

      {/* Rows */}
      {snapshots.length === 0 ? (
        <div
          style={{
            padding: "14px 14px",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "#2E2C2A",
            textAlign: "center",
          }}
        >
          Ingen lagrede snapshots. Klikk "Lagre kupong" for å ta en frysning.
        </div>
      ) : (
        <AnimatePresence>
          {snapshots.map((snap) => (
            <SnapshotRow
              key={snap.snapshot_id}
              snap={snap}
              onDelete={onDelete}
              isDeleting={deletingId === snap.snapshot_id}
            />
          ))}
        </AnimatePresence>
      )}
    </motion.div>
  );
}

// ── Save toast ────────────────────────────────────────────────────────────────

function SaveToast({ message }: { message: string | null }) {
  return (
    <AnimatePresence>
      {message && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.2 }}
          style={{
            position: "fixed",
            bottom: 24,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 50,
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "8px 14px",
            borderRadius: 7,
            border: "1px solid rgba(34,197,94,0.2)",
            background: "rgba(10,10,11,0.92)",
            backdropFilter: "blur(8px)",
          }}
        >
          <span style={{ color: "#22C55E", fontSize: 12 }}>✓</span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              fontWeight: 600,
              color: "#C8C4BC",
            }}
          >
            {message}
          </span>
        </motion.div>
      )}
    </AnimatePresence>
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

  // Save state
  const [isSaving, setIsSaving] = useState(false);
  const [saveToast, setSaveToast] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  // Saved snapshots query
  const snapshotsQuery = useQuery({
    queryKey: ["snapshots", selectedCouponId],
    queryFn: () => listSavedSnapshots({ coupon_id: selectedCouponId! }),
    enabled: !!selectedCouponId && !isApiOffline,
    staleTime: 30_000,
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

  // Save handler
  const handleSave = useCallback(async () => {
    if (!selectedCouponId || isSaving) return;
    setIsSaving(true);
    try {
      await saveCoupon({
        coupon_id: selectedCouponId,
        strategy,
        budget,
        cost_per_row: 1.0,
      });
      await queryClient.invalidateQueries({ queryKey: ["snapshots", selectedCouponId] });
      const stratLabel = strategy.charAt(0).toUpperCase() + strategy.slice(1);
      setSaveToast(`Lagret · ${stratLabel} / ${budget} kr`);
      setTimeout(() => setSaveToast(null), 2800);
    } catch {
      setSaveToast("Feil — kunne ikke lagre");
      setTimeout(() => setSaveToast(null), 3000);
    } finally {
      setIsSaving(false);
    }
  }, [selectedCouponId, strategy, budget, isSaving, queryClient]);

  // Delete handler
  const handleDelete = useCallback(async (snapshotId: string) => {
    setDeletingId(snapshotId);
    try {
      await deleteSavedSnapshot(snapshotId);
      await queryClient.invalidateQueries({ queryKey: ["snapshots", selectedCouponId] });
    } finally {
      setDeletingId(null);
    }
  }, [selectedCouponId, queryClient]);

  const snapshots = snapshotsQuery.data ?? [];

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
                onSave={selectedCouponId ? handleSave : undefined}
                isSaving={isSaving}
              />
            ) : undefined
          }
        />

        {/* Saved snapshots */}
        {selectedCouponId && (
          <SavedSnapshotsSection
            couponId={selectedCouponId}
            snapshots={snapshots}
            onDelete={handleDelete}
            deletingId={deletingId}
          />
        )}
      </main>

      {/* Toast */}
      <SaveToast message={saveToast} />

      {/* Spinner keyframe */}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
