"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn, fmtPct, fmtPvr } from "@/lib/utils";
import type { OptimizeResponse } from "@/lib/types";

function AnimatedValue({ value, className }: { value: string; className?: string }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: 3 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -3 }}
        transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
        className={cn("inline-block tabular-nums", className)}
      >
        {value}
      </motion.span>
    </AnimatePresence>
  );
}

interface MetricsRowProps {
  result: OptimizeResponse | undefined;
  isLoading?: boolean;
}

export function MetricsRow({ result, isLoading }: MetricsRowProps) {
  const showSkeleton = isLoading && !result;
  const pWinPct = result ? fmtPct(result.p_win, 2) : "—";
  const pvr     = result ? fmtPvr(result.pvr)      : "—";
  const rows    = result ? String(result.total_rows) : "—";
  const cost    = result ? `${result.total_cost} kr` : "—";
  const pvrPos  = (result?.pvr ?? 0) > 1.0;

  if (showSkeleton) {
    return (
      <div className="flex items-center gap-5 px-1 py-1">
        <div className="skeleton h-7 w-20 rounded" />
        <div className="skeleton h-7 w-20 rounded" />
        <div className="skeleton h-5 w-28 rounded" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-wrap items-baseline gap-x-2 gap-y-1 px-1"
    >
      <div className="flex items-baseline gap-1.5">
        <span className="text-[10px] font-semibold text-[#ADA9A2] uppercase tracking-widest">P(12/12)</span>
        <AnimatedValue value={pWinPct} className="text-[22px] font-bold text-[#111110] leading-none" />
      </div>

      <span className="text-[#E4E1DA] text-[16px] leading-none">·</span>

      <div className="flex items-baseline gap-1.5">
        <span className="text-[10px] font-semibold text-[#ADA9A2] uppercase tracking-widest">PVR</span>
        <AnimatedValue
          value={pvr}
          className={cn("text-[22px] font-bold leading-none", pvrPos ? "text-[#D4930A]" : "text-[#6B6862]")}
        />
      </div>

      <span className="text-[#E4E1DA] text-[16px] leading-none">·</span>

      <div className="flex items-baseline gap-1">
        <AnimatedValue value={rows} className="text-[15px] font-semibold text-[#6B6862] leading-none" />
        <span className="text-[11px] text-[#ADA9A2]">rader</span>
      </div>

      <span className="text-[#E4E1DA] text-[13px] leading-none">·</span>

      <AnimatedValue value={cost} className="text-[15px] font-semibold text-[#6B6862] leading-none" />
    </motion.div>
  );
}
