"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";
import type { Strategy } from "@/lib/types";

interface StrategySelectorProps {
  selected: Strategy;
  onSelect: (s: Strategy) => void;
  variant?: "horizontal" | "vertical";
}

const STRATEGIES: Array<{
  key: Strategy;
  badge: string;
  desc: string;
  detail: string;
}> = [
  { key: "safe",     badge: "Safe",      desc: "Treffsikker", detail: "Lavest risiko" },
  { key: "balanced", badge: "Balansert", desc: "Anbefalt",    detail: "Optimalt for de fleste" },
  { key: "jackpot",  badge: "Jackpot",   desc: "Høy risiko",  detail: "Maks forventet verdi" },
];

export function StrategySelector({ selected, onSelect, variant = "vertical" }: StrategySelectorProps) {
  if (variant === "horizontal") {
    return (
      <LayoutGroup>
        <div className="flex gap-1.5">
          {STRATEGIES.map((s) => {
            const isActive = s.key === selected;
            return (
              <motion.button
                key={s.key}
                onClick={() => onSelect(s.key)}
                whileTap={{ scale: 0.97 }}
                transition={{ duration: 0.12 }}
                className={cn(
                  "relative flex-1 text-center py-2 px-2 rounded-lg border overflow-hidden min-h-[40px]",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#111110]/20",
                  "transition-colors duration-150",
                  isActive
                    ? "bg-[#111110] border-[#111110]"
                    : "bg-white border-[#E4E1DA] hover:border-[#C0BAB0]",
                )}
              >
                <div className={cn(
                  "text-[11px] font-bold tracking-wide leading-none",
                  isActive ? "text-white" : "text-[#6B6862]",
                )}>
                  {s.badge}
                </div>
                <div className={cn(
                  "text-[9px] mt-0.5 leading-none",
                  isActive ? "text-white/60" : "text-[#ADA9A2]",
                )}>
                  {s.desc}
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
      <div className="space-y-1.5">
        {STRATEGIES.map((s) => {
          const isActive = s.key === selected;
          return (
            <motion.button
              key={s.key}
              onClick={() => onSelect(s.key)}
              whileTap={{ scale: 0.98 }}
              className={cn(
                "relative w-full py-3 px-3.5 rounded-lg border text-left",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#111110]/20",
                "transition-colors duration-150",
                isActive
                  ? "bg-[#111110] border-[#111110]"
                  : "bg-white border-[#E4E1DA] hover:border-[#C0BAB0]",
              )}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className={cn(
                    "text-[12px] font-bold tracking-wide block leading-none",
                    isActive ? "text-white" : "text-[#111110]",
                  )}>
                    {s.badge}
                  </span>
                  <span className={cn("text-[10px] mt-1 block", isActive ? "text-white/70" : "text-[#6B6862]")}>
                    {s.desc}
                  </span>
                  <span className={cn("text-[9px] mt-0.5 block", isActive ? "text-white/40" : "text-[#ADA9A2]")}>
                    {s.detail}
                  </span>
                </div>
                {isActive && <span className="w-1.5 h-1.5 rounded-full bg-[#F5C542] shrink-0 ml-2" />}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
