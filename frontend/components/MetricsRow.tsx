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
  prominent?: boolean;
  index?: number;
  isLoading?: boolean;
  tooltip?: string;
}

function MetricCard({
  label,
  value,
  sub,
  accent = "none",
  prominent = false,
  index = 0,
  isLoading,
  tooltip,
}: MetricCardProps) {
  const borderColor =
    accent === "gold"
      ? "border-amber-400/25"
      : accent === "blue"
      ? "border-sky-500/20"
      : "border-[#202020]";

  const valueColor =
    accent === "gold"
      ? "text-amber-400"
      : "text-zinc-100";

  const valueSize = prominent ? "text-[30px]" : "text-[26px]";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SPRING, delay: index * 0.06 }}
      title={tooltip}
      className={cn(
        "relative rounded-xl border overflow-hidden p-4 cursor-default bg-[#101010]",
        borderColor,
      )}
    >
      <p className="text-[9px] font-bold text-zinc-600 uppercase tracking-[1.4px] mb-2.5">
        {label}
      </p>

      {isLoading ? (
        <div className="space-y-2">
          <div className="skeleton h-8 w-20 rounded" />
          <div className="skeleton h-2.5 w-14 rounded" />
        </div>
      ) : (
        <AnimatePresence mode="wait">
          <motion.div
            key={value}
            initial={{ opacity: 0, scale: 0.94 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.97 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
          >
            <p className={cn("font-black tabular-nums leading-none tracking-tight", valueColor, valueSize)}>
              {value}
            </p>
            {sub && (
              <p className="text-[10px] text-zinc-700 mt-1.5 font-medium">{sub}</p>
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
  const pWinPct  = result ? fmtPct(result.p_win, 2) : "—";
  const pvr      = result ? fmtPvr(result.pvr) : "—";
  const rows     = result ? String(result.total_rows) : "—";
  const cost     = result ? `${result.total_cost} kr` : "—";
  const pvrPositive = (result?.pvr ?? 0) > 1.0;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
      <MetricCard
        label="P(12/12)"
        value={pWinPct}
        sub="Vinnersannsynlighet"
        accent="blue"
        prominent
        index={0}
        isLoading={showSkeleton}
        tooltip="P(12/12) — sannsynligheten for at systemet dekker alle 12 riktige utfall. Avhenger av strategi og budsjett."
      />
      <MetricCard
        label="PVR"
        value={pvr}
        sub={pvrPositive ? "Positiv pool-edge" : "Under paritetsverdi"}
        accent={pvrPositive ? "gold" : "none"}
        prominent
        index={1}
        isLoading={showSkeleton}
        tooltip="PVR (Pool Value Ratio) — modellens vinnersjanse ÷ folkets vinnersjanse. Over 1,0 betyr at kupong er mer unik enn snittet i potten. Ikke en avkastningsfaktor."
      />
      <MetricCard
        label="Rader"
        value={rows}
        sub="Kupongens bredde"
        index={2}
        isLoading={showSkeleton}
        tooltip="Antall rader i systemet — avhenger av heldekk- og halvdekk-valg."
      />
      <MetricCard
        label="Kostnad"
        value={cost}
        sub="Totalpris"
        index={3}
        isLoading={showSkeleton}
        tooltip="Totalpris (antall rader × 4 kr per rad)."
      />
    </div>
  );
}
