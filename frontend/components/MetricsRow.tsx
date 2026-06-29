"use client";

import { useEffect } from "react";
import { motion, AnimatePresence, useMotionValue, useTransform, animate } from "framer-motion";
import { cn, fmtPct, fmtPvr } from "@/lib/utils";
import type { OptimizeResponse } from "@/lib/types";

function SpringNumber({ value, format, className }: {
  value: number;
  format: (n: number) => string;
  className?: string;
}) {
  const motionValue = useMotionValue(0);
  const displayed = useTransform(motionValue, format);

  useEffect(() => {
    const animation = animate(motionValue, value, { duration: 0.75, ease: "easeOut" });
    return animation.stop;
  }, [value, motionValue]);

  return (
    <motion.span
      className={cn("inline-block tabular-nums", className)}
      style={{ fontFamily: "var(--font-mono)" }}
    >
      {displayed}
    </motion.span>
  );
}

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
        style={{ fontFamily: "var(--font-mono)" }}
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

const CELL_BASE = "flex-1 px-5 py-5 border-r border-[rgba(255,255,255,0.05)] last:border-r-0 flex flex-col gap-2";
const LABEL_CLS = "text-[8px] font-semibold text-[#2E2C2A] uppercase tracking-[0.14em] leading-none";
const EMPTY_NUM = "text-[#2E2C2A]";

export function MetricsRow({ result, isLoading }: MetricsRowProps) {
  const showSkeleton = isLoading && !result;
  const pvrPos = (result?.pvr ?? 0) > 1.0;

  if (showSkeleton) {
    return (
      <div className="animate-pulse flex items-stretch rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#0B0B0E] overflow-hidden">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className={CELL_BASE}>
            <div className="h-[8px] w-14 rounded bg-[rgba(255,255,255,0.06)]" />
            <div className="h-[28px] w-20 rounded bg-[rgba(255,255,255,0.09)]" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex items-stretch rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#0B0B0E] overflow-hidden">
      {/* P(12/12) */}
      <div className={CELL_BASE}>
        <span className={LABEL_CLS}>P(12/12)</span>
        {result ? (
          <SpringNumber
            value={result.p_win}
            format={(n) => fmtPct(n, 2)}
            className="text-[28px] font-bold text-[#E8E4DD] leading-none tracking-tight"
          />
        ) : (
          <span className={cn("text-[28px] font-bold leading-none tracking-tight", EMPTY_NUM)}>—</span>
        )}
      </div>

      {/* PVR — the signal the user cares most about */}
      <div className={CELL_BASE}>
        <span className={LABEL_CLS}>PVR</span>
        {result ? (
          <SpringNumber
            value={result.pvr ?? 0}
            format={(n) => fmtPvr(n)}
            className={cn(
              "text-[28px] font-bold leading-none tracking-tight",
              pvrPos ? "text-[#F5C030]" : "text-[#7A7673]",
            )}
          />
        ) : (
          <span className={cn("text-[28px] font-bold leading-none tracking-tight", EMPTY_NUM)}>—</span>
        )}
      </div>

      {/* Rader */}
      <div className={CELL_BASE}>
        <span className={LABEL_CLS}>Rader</span>
        <AnimatedValue
          value={result ? String(result.total_rows) : "—"}
          className={cn("text-[28px] font-bold leading-none tracking-tight", result ? "text-[#7A7673]" : EMPTY_NUM)}
        />
      </div>

      {/* Kostnad */}
      <div className={CELL_BASE}>
        <span className={LABEL_CLS}>Kostnad</span>
        <AnimatedValue
          value={result ? `${result.total_cost} kr` : "—"}
          className={cn("text-[28px] font-bold leading-none tracking-tight", result ? "text-[#7A7673]" : EMPTY_NUM)}
        />
      </div>
    </div>
  );
}
