"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn, fmtPct, fmtPvr } from "@/lib/utils";
import type { OptimizeResponse } from "@/lib/types";

const SPRING = { type: "spring", stiffness: 260, damping: 28 } as const;

interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  accent?: "gold" | "blue" | "none";
  index?: number;
  isLoading?: boolean;
}

function MetricCard({
  label,
  value,
  sub,
  accent = "none",
  index = 0,
  isLoading,
}: MetricCardProps) {
  const glowColor =
    accent === "gold"
      ? "rgba(245,197,24,0.12)"
      : accent === "blue"
      ? "rgba(96,165,250,0.1)"
      : "transparent";

  const borderActive =
    accent === "gold"
      ? "border-amber-400/25"
      : accent === "blue"
      ? "border-blue-400/20"
      : "border-white/[0.07]";

  const topLineColor =
    accent === "gold"
      ? "from-transparent via-amber-400/50 to-transparent"
      : accent === "blue"
      ? "from-transparent via-blue-400/35 to-transparent"
      : "from-transparent via-white/[0.09] to-transparent";

  const valueColor =
    accent === "gold"
      ? "bg-gradient-to-br from-amber-300 to-amber-500 bg-clip-text text-transparent"
      : "text-slate-100";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: index * 0.07 }}
      whileHover={{ y: -2, transition: { duration: 0.18 } }}
      className={cn(
        "relative rounded-xl border overflow-hidden bg-white/[0.025] p-4 cursor-default",
        "transition-colors duration-200",
        borderActive
      )}
      style={{ boxShadow: `0 0 24px ${glowColor}, inset 0 1px 0 rgba(255,255,255,0.04)` }}
    >
      {/* top accent line */}
      <div
        className={cn(
          "absolute top-0 inset-x-0 h-[1px] bg-gradient-to-r",
          topLineColor
        )}
      />

      <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest mb-3">
        {label}
      </p>

      {isLoading ? (
        <div className="space-y-2">
          <div className="skeleton h-8 w-24 rounded-lg" />
          <div className="skeleton h-3 w-16 rounded" />
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={value}
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.96 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          >
            <p
              className={cn(
                "text-[28px] font-black tabular-nums leading-none tracking-tight",
                valueColor
              )}
            >
              {value}
            </p>
            {sub && (
              <p className="text-[11px] text-slate-600 mt-2 font-medium">{sub}</p>
            )}
          </motion.div>
        </AnimatePresence>
      )}
    </motion.div>
  );
}

interface MetricsRowProps {
  result: OptimizeResponse | undefined;
  isLoading?: boolean;
}

export function MetricsRow({ result, isLoading }: MetricsRowProps) {
  const showSkeleton = isLoading && !result;
  const pWinPct = result ? fmtPct(result.p_win, 2) : "—";
  const pvr = result ? fmtPvr(result.pvr) : "—";
  const rows = result ? String(result.total_rows) : "—";
  const cost = result ? `${result.total_cost} kr` : "—";
  const pvrPositive = (result?.pvr ?? 0) > 1.0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <MetricCard
        label="P(12/12)"
        value={pWinPct}
        sub="Vinnersannsynlighet"
        accent="blue"
        index={0}
        isLoading={showSkeleton}
      />
      <MetricCard
        label="PVR"
        value={pvr}
        sub={pvrPositive ? "Positiv pool-edge ↑" : "Under paritetsverdi"}
        accent={pvrPositive ? "gold" : "none"}
        index={1}
        isLoading={showSkeleton}
      />
      <MetricCard
        label="Rader"
        value={rows}
        sub="Kupongens bredde"
        index={2}
        isLoading={showSkeleton}
      />
      <MetricCard
        label="Kostnad"
        value={cost}
        sub="Totalpris"
        index={3}
        isLoading={showSkeleton}
      />
    </div>
  );
}
