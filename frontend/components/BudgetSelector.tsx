"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";

interface BudgetSelectorProps {
  budgets: number[];
  selected: number;
  onSelect: (b: number) => void;
  variant?: "horizontal" | "grid";
}

const LABELS: Record<number, string> = {
  32:  "Minimal",
  96:  "Moderat",
  192: "Anbefalt",
  384: "Aggressiv",
};

export function BudgetSelector({ budgets, selected, onSelect, variant = "grid" }: BudgetSelectorProps) {
  if (variant === "horizontal") {
    return (
      <LayoutGroup>
        <div className="flex gap-1.5">
          {budgets.map((b) => {
            const isActive = b === selected;
            return (
              <motion.button
                key={b}
                onClick={() => onSelect(b)}
                whileTap={{ scale: 0.97 }}
                transition={{ duration: 0.12 }}
                className={cn(
                  "relative flex-1 text-center py-2 px-2.5 rounded-lg border overflow-hidden min-h-[40px]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D4930A]/30",
                  "transition-colors duration-150",
                  isActive
                    ? "bg-[#F5C542] border-[#E8B400] text-[#111110]"
                    : "bg-white border-[#E4E1DA] text-[#6B6862] hover:border-[#C0BAB0] hover:text-[#111110]",
                )}
              >
                <div className={cn("text-[12px] font-bold tabular-nums leading-none", isActive ? "text-[#111110]" : "")}>
                  {b} kr
                </div>
                <div className={cn("text-[9px] mt-0.5 leading-none", isActive ? "text-[#6B4C00]" : "text-[#ADA9A2]")}>
                  {LABELS[b] ?? String(b)}
                </div>
              </motion.button>
            );
          })}
        </div>
      </LayoutGroup>
    );
  }

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
                "relative py-2.5 px-3 rounded-lg border text-left",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#D4930A]/30",
                "transition-colors duration-150",
                isActive
                  ? "bg-[#F5C542] border-[#E8B400] text-[#111110]"
                  : "bg-white border-[#E4E1DA] text-[#6B6862] hover:border-[#C0BAB0] hover:text-[#111110]",
              )}
            >
              <div className={cn("text-[13px] font-bold tabular-nums leading-none", isActive ? "text-[#111110]" : "")}>
                {b} kr
              </div>
              <div className={cn("text-[10px] mt-1", isActive ? "text-[#6B4C00]" : "text-[#ADA9A2]")}>
                {LABELS[b] ?? String(b)}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
