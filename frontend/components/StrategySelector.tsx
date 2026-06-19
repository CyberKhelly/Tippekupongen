"use client";

import { motion, LayoutGroup } from "framer-motion";
import { ShieldCheck, SlidersHorizontal, Zap } from "lucide-react";
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
  objective: string;
  Icon: React.ElementType;
}[] = [
  {
    key: "safe",
    badge: "SAFE",
    desc: "Maksimerer vinnersannsynlighet",
    objective: "Maks P(12/12)",
    Icon: ShieldCheck,
  },
  {
    key: "balanced",
    badge: "BALANSERT",
    desc: "Balanse mellom sjanse og pool-unikhet",
    objective: "P(12/12)⁰·⁹ × PVR⁰·¹",
    Icon: SlidersHorizontal,
  },
  {
    key: "jackpot",
    badge: "JACKPOT",
    desc: "Maksimerer forventet utdeling",
    objective: "Maks pool-verdi",
    Icon: Zap,
  },
];

export function StrategySelector({ selected, onSelect }: StrategySelectorProps) {
  return (
    <LayoutGroup>
      <div className="space-y-2">
        {STRATEGIES.map((s) => {
          const isActive = s.key === selected;
          return (
            <motion.button
              key={s.key}
              onClick={() => onSelect(s.key)}
              whileHover={{ x: 2 }}
              whileTap={{ scale: 0.985 }}
              transition={{ duration: 0.15 }}
              className={cn(
                "relative w-full text-left p-3 rounded-xl border overflow-hidden",
                "transition-colors duration-150 group",
                isActive
                  ? "border-amber-400/[0.3]"
                  : "border-white/[0.05] hover:border-white/[0.09]"
              )}
            >
              {/* animated background fill */}
              {isActive && (
                <motion.div
                  layoutId="strategy-bg"
                  className="absolute inset-0 bg-amber-400/[0.06]"
                  style={{
                    boxShadow:
                      "0 0 24px rgba(245,197,24,0.05), inset 0 1px 0 rgba(245,197,24,0.08)",
                  }}
                  transition={{ type: "spring", stiffness: 300, damping: 35 }}
                />
              )}

              {/* non-active base */}
              {!isActive && (
                <div className="absolute inset-0 bg-white/[0.02] group-hover:bg-white/[0.04] transition-colors duration-150" />
              )}

              <div className="relative flex items-center gap-2 mb-1.5">
                <s.Icon
                  className={cn(
                    "w-3.5 h-3.5 shrink-0 transition-colors",
                    isActive ? "text-amber-400" : "text-slate-600 group-hover:text-slate-500"
                  )}
                />
                <span
                  className={cn(
                    "text-[10px] font-bold tracking-[0.12em]",
                    isActive ? "text-amber-400" : "text-slate-600 group-hover:text-slate-500"
                  )}
                >
                  {s.badge}
                </span>
              </div>

              <div
                className={cn(
                  "relative text-[12px] font-medium leading-snug",
                  isActive ? "text-slate-200" : "text-slate-500 group-hover:text-slate-400"
                )}
              >
                {s.desc}
              </div>
              <div className="relative text-[10px] text-slate-700 mt-0.5 font-mono">
                {s.objective}
              </div>
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
