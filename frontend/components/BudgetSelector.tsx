"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";

interface BudgetSelectorProps {
  budgets: number[];
  selected: number;
  onSelect: (b: number) => void;
}

const LABELS: Record<number, string> = {
  32:  "Minimal",
  96:  "Moderat",
  192: "Anbefalt",
  384: "Aggressiv",
};

export function BudgetSelector({ budgets, selected, onSelect }: BudgetSelectorProps) {
  return (
    <LayoutGroup>
      <div className="grid grid-cols-2 gap-1.5">
        {budgets.map((b, i) => {
          const isActive = b === selected;
          return (
            <motion.button
              key={b}
              onClick={() => onSelect(b)}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.04, duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              whileTap={{ scale: 0.97 }}
              className={cn(
                "relative py-2.5 px-3 rounded-lg border text-left overflow-hidden",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/50",
                "transition-colors duration-150 group",
                isActive
                  ? "border-amber-400/[0.28]"
                  : "border-[#202020] hover:border-[#2c2c2c]"
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="budget-bg"
                  className="absolute inset-0 bg-amber-400/[0.05]"
                  transition={{ type: "spring", stiffness: 340, damping: 38 }}
                />
              )}
              {!isActive && (
                <div className="absolute inset-0 bg-[#101010] group-hover:bg-[#131313] transition-colors" />
              )}

              <div
                className={cn(
                  "relative text-[13px] font-bold tabular-nums leading-none",
                  isActive ? "text-amber-400" : "text-zinc-400 group-hover:text-zinc-300"
                )}
              >
                {b} kr
              </div>
              <div className={cn("relative text-[10px] mt-1", isActive ? "text-zinc-500" : "text-zinc-600 group-hover:text-zinc-500")}>
                {LABELS[b] ?? String(b)}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
