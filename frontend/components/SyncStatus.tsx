"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, ChevronDown, ChevronUp, AlertCircle } from "lucide-react";
import { cn, formatRelative, formatUntil } from "@/lib/utils";
import type { SyncStatus } from "@/lib/types";

interface SyncStatusProps {
  status: SyncStatus | undefined;
  isLoading?: boolean;
}

const JOB_LABEL: Record<string, string> = {
  nt_refresh: "NT-data",
  odds_refresh: "Odds",
  daily_sync: "Full sync",
  refresh_coupons: "Kuponger",
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 min-w-0">
      <span className="text-[10px] text-slate-600 shrink-0">{label}</span>
      <span className="text-[10px] font-medium text-slate-400 tabular-nums truncate text-right">
        {value}
      </span>
    </div>
  );
}

export function SyncStatusPanel({ status, isLoading }: SyncStatusProps) {
  const [expanded, setExpanded] = useState(false);

  const isRunning = status?.is_running ?? false;
  const hasError = status?.last_success === false && !!status?.last_error;
  const nChanges = status?.n_public_pct_changes ?? 0;
  const turnoverEntries = Object.entries(status?.turnover ?? {});
  const totalTurnover = turnoverEntries.reduce((s, [, v]) => s + v, 0);

  return (
    <div className="relative glass rounded-xl overflow-hidden card-top-line">
      {/* Header row */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          {/* Spinner / idle dot / error */}
          <AnimatePresence mode="wait">
            {isRunning ? (
              <motion.span
                key="spin"
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className="text-amber-400"
              >
                <RefreshCw className="w-3 h-3 animate-spin" />
              </motion.span>
            ) : hasError ? (
              <motion.span
                key="err"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-red-400"
              >
                <AlertCircle className="w-3 h-3" />
              </motion.span>
            ) : (
              <motion.span
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="relative flex h-1.5 w-1.5 shrink-0"
              >
                <span className="absolute inset-0 rounded-full bg-emerald-400 opacity-40 animate-ping" />
                <span className="relative rounded-full h-1.5 w-1.5 bg-emerald-400" />
              </motion.span>
            )}
          </AnimatePresence>

          <span className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest">
            {isRunning
              ? `Synkroniserer${status?.current_job ? ` (${JOB_LABEL[status.current_job] ?? status.current_job})` : ""}…`
              : "Dataferskhet"}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {nChanges > 0 && !isRunning && (
            <motion.span
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-amber-400/[0.1] border border-amber-400/[0.2] text-amber-300 tabular-nums"
            >
              {nChanges} endring{nChanges !== 1 ? "er" : ""}
            </motion.span>
          )}
          {expanded ? (
            <ChevronUp className="w-3 h-3 text-slate-700" />
          ) : (
            <ChevronDown className="w-3 h-3 text-slate-700" />
          )}
        </div>
      </button>

      {/* Expandable body */}
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-3 space-y-1.5 border-t border-white/[0.05]">
              <div className="h-2" />

              {isLoading ? (
                <div className="space-y-2">
                  {[80, 64, 72].map((w, i) => (
                    <div key={i} className="skeleton h-3 rounded" style={{ width: w + "%" }} />
                  ))}
                </div>
              ) : (
                <>
                  <Row
                    label="NT-prosenter"
                    value={formatRelative(status?.last_nt_refresh_at)}
                  />
                  <Row
                    label="Odds"
                    value={formatRelative(status?.last_odds_refresh_at)}
                  />
                  {status?.next_nt_refresh_at && (
                    <Row
                      label="Neste sjekk"
                      value={formatUntil(status.next_nt_refresh_at)}
                    />
                  )}
                  {totalTurnover > 0 && (
                    <Row
                      label="Omsetning"
                      value={
                        totalTurnover >= 1_000_000
                          ? `${(totalTurnover / 1_000_000).toFixed(2)}M kr`
                          : `${Math.round(totalTurnover / 1_000)}k kr`
                      }
                    />
                  )}
                  {nChanges > 0 && (
                    <Row
                      label="Folket-endringer"
                      value={`${nChanges} kamp${nChanges !== 1 ? "er" : ""}`}
                    />
                  )}
                  {hasError && (
                    <p className="text-[9px] text-red-400/80 mt-1 leading-snug truncate">
                      {status?.last_error}
                    </p>
                  )}
                </>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
