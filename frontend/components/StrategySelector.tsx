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
  { key: "balanced", badge: "Balansert", desc: "Anbefalt",   detail: "Optimalt for de fleste" },
  { key: "jackpot",  badge: "Jackpot",   desc: "Høy risiko", detail: "Maks forventet verdi" },
];

export function StrategySelector({ selected, onSelect, variant = "vertical" }: StrategySelectorProps) {
  if (variant === "horizontal") {
    return (
      <LayoutGroup id="strategy-h">
        <div className="flex items-end gap-6">
          {STRATEGIES.map((s) => {
            const isActive = s.key === selected;
            return (
              <button
                key={s.key}
                onClick={() => onSelect(s.key)}
                className={cn(
                  "relative pb-2.5 text-[12px] font-semibold transition-colors duration-150",
                  "focus-visible:outline-none focus-visible:ring-0",
                  isActive ? "text-[#E8E4DD]" : "text-[#4A4744] hover:text-[#7A7673]",
                )}
              >
                {isActive && (
                  <motion.div
                    layoutId="strategy-underline-h"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-[#F5C030] rounded-full"
                    transition={{ type: "spring", stiffness: 400, damping: 35 }}
                  />
                )}
                {s.badge}
              </button>
            );
          })}
        </div>
      </LayoutGroup>
    );
  }

  return (
    <LayoutGroup id="strategy-v">
      <div className="space-y-0.5">
        {STRATEGIES.map((s) => {
          const isActive = s.key === selected;
          return (
            <button
              key={s.key}
              onClick={() => onSelect(s.key)}
              className={cn(
                "relative w-full py-2.5 pl-4 pr-3 rounded-md text-left transition-colors duration-150",
                "focus-visible:outline-none",
                isActive
                  ? "bg-[#1C1C1C] text-[#E8E4DD]"
                  : "text-[#4A4744] hover:bg-[#141414] hover:text-[#7A7673]",
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="strategy-line-v"
                  className="absolute left-0 top-2 bottom-2 w-[2px] bg-[#F5C030] rounded-r-full"
                  transition={{ type: "spring", stiffness: 400, damping: 35 }}
                />
              )}
              <div>
                <span className="text-[12px] font-bold block leading-none">
                  {s.badge}
                </span>
                <span className="text-[10px] mt-1 block text-[#4A4744]">
                  {s.desc}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
