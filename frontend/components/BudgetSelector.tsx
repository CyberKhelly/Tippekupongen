"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";

interface BudgetSelectorProps {
  budgets: number[];
  selected: number;
  onSelect: (b: number) => void;
}

const LABELS: Record<number, { name: string; sub: string }> = {
  32:  { name: "Minimal",   sub: "Lavrisiko" },
  96:  { name: "Moderat",   sub: "Balansert" },
  192: { name: "Anbefalt",  sub: "Optimal" },
  384: { name: "Aggressiv", sub: "Maksdekning" },
};

export function BudgetSelector({ budgets, selected, onSelect }: BudgetSelectorProps) {
  return (
    <LayoutGroup>
      <div className="grid grid-cols-2 gap-2">
        {budgets.map((b, i) => {
          const isActive = b === selected;
          const meta = LABELS[b] ?? { name: String(b), sub: "" };
          return (
            <motion.button
              key={b}
              onClick={() => onSelect(b)}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.05, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.97 }}
              className={cn(
                "relative py-2.5 px-3 rounded-lg border text-left overflow-hidden",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50",
                "transition-colors duration-150 group",
                isActive
                  ? "border-amber-400/[0.3]"
                  : "border-white/[0.05] hover:border-white/[0.09]"
              )}
            >
              {/* animated background */}
              {isActive && (
                <motion.div
                  layoutId="budget-bg"
                  className="absolute inset-0 bg-amber-400/[0.06]"
                  style={{
                    boxShadow: "inset 0 1px 0 rgba(245,197,24,0.08)",
                  }}
                  transition={{ type: "spring", stiffness: 340, damping: 38 }}
                />
              )}
              {!isActive && (
                <div className="absolute inset-0 bg-white/[0.02] group-hover:bg-white/[0.04] transition-colors" />
              )}

              <div
                className={cn(
                  "relative text-[13px] font-bold tabular-nums leading-none",
                  isActive ? "text-amber-400" : "text-slate-400 group-hover:text-slate-300"
                )}
              >
                {b} kr
              </div>
              <div className="relative text-[10px] text-slate-600 mt-1 font-medium">
                {meta.name}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
