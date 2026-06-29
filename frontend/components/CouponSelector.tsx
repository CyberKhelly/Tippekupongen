"use client";

import { motion, LayoutGroup } from "framer-motion";
import { cn, couponLabel } from "@/lib/utils";
import type { CouponListItem } from "@/lib/types";

interface CouponSelectorProps {
  coupons: CouponListItem[];
  selected: string | null;
  onSelect: (id: string) => void;
  isLoading?: boolean;
}

const DAY_LABEL: Record<string, string> = {
  MIDWEEK:  "Midtuke",
  SATURDAY: "Lørdag",
  SUNDAY:   "Søndag",
};

export function CouponSelector({ coupons, selected, onSelect, isLoading }: CouponSelectorProps) {
  if (isLoading) {
    return (
      <div className="flex gap-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="skeleton h-9 w-28 rounded-lg" style={{ animationDelay: `${i * 80}ms` }} />
        ))}
      </div>
    );
  }

  if (!coupons.length) return null;

  return (
    <LayoutGroup>
      <div role="tablist" aria-label="Velg kupong" className="flex items-center gap-1.5 flex-wrap">
        {coupons.map((c, i) => {
          const isActive = c.coupon_id === selected;
          const label = c.day_type ? DAY_LABEL[c.day_type] : couponLabel(c.coupon_id);
          return (
            <motion.button
              key={c.coupon_id}
              role="tab"
              aria-selected={isActive}
              onClick={() => onSelect(c.coupon_id)}
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
              whileTap={{ scale: 0.97 }}
              className={cn(
                "relative px-4 py-2 text-[13px] font-semibold rounded-lg border transition-colors duration-150",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#F5C030]/20",
                isActive
                  ? "bg-[rgba(255,255,255,0.07)] border-[rgba(255,255,255,0.14)] text-[#E8E4DD]"
                  : "bg-transparent border-[rgba(255,255,255,0.07)] text-[#4A4744] hover:text-[#7A7673] hover:border-[rgba(255,255,255,0.12)]",
              )}
            >
              {label}
            </motion.button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}
