"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { getGenerationDetail } from "@/lib/api";
import type { GenerationSummary, GenerationDetail } from "@/lib/types";
import { cn, sortSigns } from "@/lib/utils";

// ── Constants ─────────────────────────────────────────────────────────────────

const SHORT_LABEL: Record<string, string> = {
  safe:     "Treffsikker",
  balanced: "Balansert",
  jackpot:  "Risiko",
};

const COUPON_IDENTITY: Record<string, { name: string; accent: string; initial: string }> = {
  SATURDAY: { name: "Lørdagskupongen", accent: "#1D4ED8", initial: "L" },
  SUNDAY:   { name: "Søndagskupongen", accent: "#15803D", initial: "S" },
  MIDWEEK:  { name: "Midtukekupongen", accent: "#D4930A", initial: "M" },
};
const DEFAULT_IDENTITY = { name: "Kupong", accent: "#D4930A", initial: "K" };

// ── VolatilityIcon ────────────────────────────────────────────────────────────

function VolatilityIcon({ treff }: { treff: number | null }) {
  const barCount = treff === 12 ? 3 : (treff ?? 0) >= 10 ? 2 : (treff ?? 0) >= 8 ? 1 : 0;
  const gold = treff === 12;
  return (
    <div className="flex items-end gap-0.5 h-4">
      {Array.from({ length: 3 }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "w-1 rounded-full",
            i === 0 ? "h-2" : i === 1 ? "h-3" : "h-4",
            i < barCount
              ? gold ? "bg-[#D4930A]" : "bg-[#ADA9A2]"
              : "bg-[#EDE9E2]",
          )}
        />
      ))}
    </div>
  );
}

// ── Formatters ────────────────────────────────────────────────────────────────

function formatDate(utc: string) {
  return new Date(utc).toLocaleDateString("no-NO", { day: "numeric", month: "short" });
}
function fmtPvr(v: number | null | undefined) {
  return v == null ? "—" : `${v.toFixed(2)}×`;
}
function daysUntil(utc: string): string {
  const diff = new Date(utc).getTime() - Date.now();
  if (diff <= 0) return "Utgått";
  const d = Math.floor(diff / 86_400_000);
  const h = Math.floor((diff % 86_400_000) / 3_600_000);
  if (d === 0) return `${h}t`;
  return `${d}d`;
}

// ── Types + grouping ──────────────────────────────────────────────────────────

type CouponGroup = {
  coupon_id: string;
  week: number;
  year: number;
  day_type: string | null;
  deadline_utc: string;
  generations: GenerationSummary[];
};

function groupByCoupon(gens: GenerationSummary[]): CouponGroup[] {
  const seen = new Map<string, CouponGroup>();
  const result: CouponGroup[] = [];
  for (const g of gens) {
    if (!seen.has(g.coupon_id)) {
      seen.set(g.coupon_id, {
        coupon_id: g.coupon_id,
        week: g.week,
        year: g.year,
        day_type: g.day_type,
        deadline_utc: g.deadline_utc,
        generations: [],
      });
      result.push(seen.get(g.coupon_id)!);
    }
    seen.get(g.coupon_id)!.generations.push(g);
  }
  return result;
}

// ── ExpandedResults ───────────────────────────────────────────────────────────

function ExpandedResults({ generationId }: { generationId: string }) {
  const { data, isLoading } = useQuery<GenerationDetail>({
    queryKey: ["gen-detail", generationId],
    queryFn: () => getGenerationDetail(generationId),
    staleTime: 10 * 60_000,
    enabled: !!generationId,
  });

  if (isLoading) {
    return <div className="px-4 pb-4 text-sm text-[#ADA9A2] animate-pulse">Laster…</div>;
  }
  if (!data) return null;

  return (
    <div className="px-4 pb-4 pt-2 space-y-1">
      {data.picks.map((p) => {
        const covered = p.covered === true;
        const missed  = p.covered === false && p.result_1x2 != null;
        const score   = p.home_score != null ? `${p.home_score}–${p.away_score}` : null;
        return (
          <div
            key={p.match_number}
            className={cn(
              "flex items-center gap-2 py-1.5 px-2 rounded-lg text-sm",
              covered ? "bg-[#DCFCE7]" : missed ? "bg-[#FEE2E2]" : "bg-transparent",
            )}
          >
            <span className="text-[#C8C4BC] tabular-nums w-4 shrink-0 text-xs">{p.match_number}</span>
            <span className="text-[#6B6862] flex-1 truncate text-xs">
              {p.home_name} – {p.away_name}
            </span>
            <span className={cn(
              "text-xs font-semibold tabular-nums shrink-0",
              covered ? "text-[#15803D]" : missed ? "text-[#C42B2B]" : "text-[#ADA9A2]",
            )}>
              {sortSigns(p.selected_outcomes).join("/")}
            </span>
            {score && (
              <span className="text-[#ADA9A2] tabular-nums text-xs shrink-0">{score}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Framer Motion variants ────────────────────────────────────────────────────

const containerVariants = {
  hidden:  { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
};
const itemVariants = {
  hidden:  { y: 16, opacity: 0 },
  visible: { y: 0, opacity: 1, transition: { type: "spring" as const, stiffness: 120, damping: 16 } },
};

// ── CouponCard ────────────────────────────────────────────────────────────────

function CouponCard({ group }: { group: CouponGroup }) {
  const [open, setOpen] = useState(false);

  const identity = group.day_type
    ? (COUPON_IDENTITY[group.day_type] ?? DEFAULT_IDENTITY)
    : DEFAULT_IDENTITY;

  const evaledGens = group.generations.filter((g) => g.correct_picks != null);
  const bestGen = evaledGens.reduce<GenerationSummary | null>((best, g) => {
    if (!best || (g.correct_picks ?? 0) > (best.correct_picks ?? 0)) return g;
    return best;
  }, null);

  const isEvaluated = evaledGens.length > 0;
  const treff   = bestGen?.correct_picks ?? null;
  const pvrVal  = bestGen?.pvr ?? null;
  const stratName = bestGen ? (SHORT_LABEL[bestGen.strategy] ?? bestGen.strategy) : "—";

  const treffColor =
    treff === 12         ? "text-[#D4930A]"
    : treff != null && treff >= 10 ? "text-[#15803D]"
    : treff != null && treff >= 8  ? "text-[#6B6862]"
    : "text-[#ADA9A2]";

  return (
    <motion.div
      variants={itemVariants}
      className="bg-white border border-[#E4E1DA] rounded-2xl shadow-card hover:border-[#C0BAB0] transition-colors duration-150 overflow-hidden cursor-pointer"
      onClick={() => { if (isEvaluated && bestGen) setOpen((v) => !v); }}
    >
      <div className="p-4">
        {/* Week + date/countdown + bars */}
        <div className="flex justify-between items-center mb-3">
          <div className="flex items-center gap-2">
            <p className="text-[11px] font-medium text-[#ADA9A2]">Uke {group.week} · {group.year}</p>
            {isEvaluated ? (
              <span
                className="text-[10px] font-semibold px-2 py-0.5 rounded-md"
                style={{ color: identity.accent, background: identity.accent + "18" }}
              >
                {formatDate(group.deadline_utc)}
              </span>
            ) : (
              <span className="text-[10px] font-semibold text-[#6B6862] bg-[#FAF9F7] border border-[#E4E1DA] px-2 py-0.5 rounded-md">
                {daysUntil(group.deadline_utc)} igjen
              </span>
            )}
          </div>
          <VolatilityIcon treff={treff} />
        </div>

        {/* Identity circle + name */}
        <div className="flex items-center gap-3 mb-4">
          <div
            className="h-8 w-8 rounded-full shrink-0 flex items-center justify-center text-[11px] font-black"
            style={{
              background: identity.accent + "18",
              border: `1.5px solid ${identity.accent}44`,
              color: identity.accent,
            }}
          >
            {identity.initial}
          </div>
          <h3 className="font-semibold text-[#111110] truncate text-[13px]">{identity.name}</h3>
        </div>

        {/* 3-col grid */}
        <div className="grid grid-cols-3 text-center text-sm divide-x divide-[#F0EDE8]">
          <div className="pr-2">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-[#ADA9A2]">Treff</p>
            <p className={cn("font-bold mt-1 text-[15px] tabular-nums leading-none", treffColor)}>
              {treff != null ? `${treff}/12` : "—"}
            </p>
          </div>
          <div className="px-2">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-[#ADA9A2]">Strategi</p>
            <p className="font-semibold text-[#111110] mt-1 text-[11px] leading-tight">{stratName}</p>
          </div>
          <div className="pl-2">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-[#ADA9A2]">PVR</p>
            <p className={cn("font-bold mt-1 text-[15px] tabular-nums leading-none", pvrVal != null && pvrVal > 1 ? "text-[#D4930A]" : "text-[#ADA9A2]")}>
              {fmtPvr(pvrVal)}
            </p>
          </div>
        </div>
      </div>

      <AnimatePresence>
        {open && bestGen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="overflow-hidden border-t border-[#EDE9E2]"
            onClick={(e) => e.stopPropagation()}
          >
            <ExpandedResults generationId={bestGen.generation_id} />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ── CouponEventRail ───────────────────────────────────────────────────────────

export function CouponEventRail({ data }: { data: GenerationSummary[] }) {
  const groups = groupByCoupon(data)
    .sort((a, b) => new Date(b.deadline_utc).getTime() - new Date(a.deadline_utc).getTime());

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-[#E4E1DA] bg-white px-6 py-10 text-center">
        <p className="text-[#ADA9A2] text-sm">Ingen kuponger ennå.</p>
      </div>
    );
  }

  return (
    <motion.div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      {groups.map((group) => (
        <CouponCard key={group.coupon_id} group={group} />
      ))}
    </motion.div>
  );
}
