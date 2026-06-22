"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn } from "@/lib/utils";
import type { Strategy } from "@/lib/types";

interface StrategySelectorProps {
  selected: Strategy;
  onSelect: (s: Strategy) => void;
}

const STRATEGIES: {
  key: Strategy;
  badge: string;
  desc: string;
}[] = [
  { key: "safe", badge: "SAFE", desc: "Treffsikker" },
  { key: "balanced", badge: "BALANSERT", desc: "Anbefalt" },
  { key: "jackpot", badge: "JACKPOT", desc: "Risiko" },
];

export function StrategySelector({ selected, onSelect }: StrategySelectorProps) {
  return (
    <LayoutGroup>
      <div className="space-y-1.5">
        {STRATEGIES.map((s) => {
          const isActive = s.key === selected;
          return (
            <motion.button
              key={s.key}
              onClick={() => onSelect(s.key)}
              whileTap={{ scale: 0.985 }}
              transition={{ duration: 0.12 }}
              className={cn(
                "relative w-full text-left px-3 py-2.5 rounded-lg border overflow-hidden",
                "transition-colors duration-150 group",
                isActive
                  ? "border-amber-400/[0.28]"
                  : "border-[#202020] hover:border-[#2c2c2c]"
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="strategy-bg"
                  className="absolute inset-0 bg-amber-400/[0.05]"
                  transition={{ type: "spring", stiffness: 300, damping: 35 }}
                />
              )}
              {!isActive && (
                <div className="absolute inset-0 bg-[#101010] group-hover:bg-[#131313] transition-colors duration-150" />
              )}

              <div className="relative flex items-center justify-between">
                <span
                  className={cn(
                    "text-[10px] font-bold tracking-[0.12em]",
                    isActive ? "text-amber-400" : "text-zinc-600 group-hover:text-zinc-500"
                  )}
                >
                  {s.badge}
                </span>
                {isActive && (
                  <span className="w-1 h-1 rounded-full bg-amber-400/60" />
                )}
              </div>

              <div
                className={cn(
                  "relative text-[12px] font-medium mt-0.5 leading-snug",
                  isActive ? "text-zinc-200" : "text-zinc-500 group-hover:text-zinc-400"
                )}
              >
                {s.desc}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
