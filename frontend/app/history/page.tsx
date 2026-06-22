"use client";

import { useState, Fragment } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { LogoMark } from "@/components/LogoMark";
import {
  getHistory,
  getHistoryCoupon,
  getHistoryStrategyPerformance,
  getHistoryCdsValidation,
  getHistoryNtComparison,
  getStrategyAnalytics,
  getGenerations,
  getGenerationDetail,
} from "@/lib/api";
import type {
  GenerationAnalytics,
  GenerationSummary,
  GenerationDetail,
  HistoryCouponItem,
  HistoryCouponDetail,
  HistoryPickItem,
  StrategyPerformance,
  CdsValidationBucket,
  NtComparison,
} from "@/lib/types";

// ── Formatting helpers ────────────────────────────────────────────────────────

function pct(v: number | null | undefined, dec = 1) {
  return v == null ? "—" : `${(v * 100).toFixed(dec)}%`;
}
function pvr(v: number | null | undefined) {
  return v == null ? "—" : `${v.toFixed(2)}×`;
}
function nok(v: number | null | undefined) {
  return v == null ? "—" : `${Math.round(v).toLocaleString("no-NO")} NOK`;
}
function fracs(n: number | null | undefined, d: number | null | undefined) {
  if (n == null || d == null) return "—";
  return `${n}/${d}`;
}

const STRATEGY_LABEL: Record<string, string> = {
  safe: "Treffsikker",
  balanced: "Anbefalt",
  jackpot: "Risiko",
  value: "Verdi",
};

const DAY_LABEL: Record<string, string> = {
  MIDWEEK: "Midtuke",
  SATURDAY: "Lørdag",
  SUNDAY: "Søndag",
};

// ── Small reusable components ─────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { bg: string; text: string; label: string }> = {
    complete: { bg: "bg-emerald-950/50 border-emerald-800/30", text: "text-emerald-400", label: "Fullstendig" },
    partial:  { bg: "bg-amber-950/50 border-amber-800/30",     text: "text-amber-400",   label: "Delvis" },
    pending:  { bg: "bg-zinc-900/40 border-zinc-800/30",       text: "text-zinc-600",    label: "Venter" },
  };
  const c = cfg[status] ?? cfg.pending;
  return (
    <span className={`inline-flex items-center h-5 px-2 rounded border text-[9px] font-bold tracking-wide ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function StrategyBadge({ strategy }: { strategy: string | null }) {
  if (!strategy) return <span className="text-zinc-700">—</span>;
  const cfg: Record<string, string> = {
    safe:     "bg-sky-950/50 border-sky-800/30 text-sky-400",
    balanced: "bg-violet-950/50 border-violet-800/30 text-violet-400",
    jackpot:  "bg-amber-950/50 border-amber-800/30 text-amber-400",
    value:    "bg-emerald-950/50 border-emerald-800/30 text-emerald-400",
  };
  const cls = cfg[strategy] ?? "bg-zinc-900/40 border-zinc-800/30 text-zinc-400";
  return (
    <span className={`inline-flex items-center h-5 px-2 rounded border text-[9px] font-bold tracking-wide ${cls}`}>
      {STRATEGY_LABEL[strategy] ?? strategy}
    </span>
  );
}

function SectionHead({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="font-display text-xs font-semibold tracking-widest uppercase text-zinc-500">
        {children}
      </span>
      <div className="flex-1 h-px bg-[#202020]" />
    </div>
  );
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      scope="col"
      className={`px-3 py-2 text-[9px] font-bold uppercase tracking-[1.2px] text-zinc-700 bg-[#0a0a0a] border-b border-[#202020] whitespace-nowrap ${right ? "text-right" : "text-left"}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  right,
  dim,
  className = "",
}: {
  children: React.ReactNode;
  right?: boolean;
  dim?: boolean;
  className?: string;
}) {
  return (
    <td
      className={`px-3 py-[6px] text-[11.5px] border-b border-[#171717] align-middle ${right ? "text-right" : ""} ${dim ? "text-zinc-700" : "text-zinc-300"} ${className}`}
    >
      {children}
    </td>
  );
}

// ── SVG Sparkline ─────────────────────────────────────────────────────────────

function Sparkline({
  values,
  color,
  height = 32,
  showDots = true,
}: {
  values: number[];
  color: string;
  height?: number;
  showDots?: boolean;
}) {
  if (values.length < 2) {
    return <span className="text-[10px] text-zinc-700">Trenger mer data</span>;
  }

  const w = 200;
  const h = height;
  const pad = 4;
  const innerW = w - pad * 2;
  const innerH = h - pad * 2;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 0.01;

  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * innerW;
    const y = pad + (1 - (v - min) / range) * innerH;
    return { x, y, v };
  });

  const polyline = pts.map((p) => `${p.x},${p.y}`).join(" ");
  const last = pts[pts.length - 1];

  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      width="100%"
      height={h}
      style={{ overflow: "visible" }}
      aria-hidden
    >
      {/* Zero or reference line at bottom */}
      <line
        x1={pad} y1={pad + innerH} x2={pad + innerW} y2={pad + innerH}
        stroke="#202020" strokeWidth="1"
      />
      {/* Sparkline */}
      <polyline
        points={polyline}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.85"
      />
      {/* Dots */}
      {showDots && pts.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="2.5" fill={color} opacity="0.7" />
      ))}
      {/* Last-point highlight */}
      {last && (
        <circle cx={last.x} cy={last.y} r="3.5" fill={color} opacity="1" />
      )}
    </svg>
  );
}

// ── Trend Charts ─────────────────────────────────────────────────────────────

function TrendCharts({ coupons }: { coupons: HistoryCouponItem[] }) {
  const evaluated = coupons
    .filter((c) => c.hit_rate != null)
    .sort((a, b) => new Date(a.deadline_utc).getTime() - new Date(b.deadline_utc).getTime())
    .slice(-15);

  if (evaluated.length < 2) {
    return (
      <div className="rounded-xl border border-[#202020] bg-[#101010] p-6 text-center">
        <p className="text-[11px] text-zinc-600">
          Trenger minst 2 evaluerte kuponger for trendvisning.
        </p>
      </div>
    );
  }

  const hitRates  = evaluated.map((c) => (c.hit_rate ?? 0) * 100);
  const pvrValues = evaluated.map((c) => c.pvr_at_save ?? 1.0);

  const latestHit = hitRates[hitRates.length - 1];
  const latestPvr = pvrValues[pvrValues.length - 1];

  const avgHit = hitRates.reduce((a, b) => a + b, 0) / hitRates.length;

  const charts = [
    {
      label: "Treffrate",
      sub: `Snitt ${avgHit.toFixed(0)}% · Siste ${latestHit.toFixed(0)}%`,
      values: hitRates,
      color: "#38bdf8",
      unit: "%",
    },
    {
      label: "PVR over tid",
      sub: `Siste ${latestPvr.toFixed(2)}× · Referanse 1.00×`,
      values: pvrValues,
      color: "#F5C542",
      unit: "×",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {charts.map((c) => (
        <div key={c.label} className="rounded-xl border border-[#202020] bg-[#101010] p-4">
          <div className="mb-1">
            <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-[1.2px]">{c.label}</p>
            <p className="text-[9px] text-zinc-700 mt-0.5">{c.sub}</p>
          </div>
          <div className="mt-3">
            <Sparkline values={c.values} color={c.color} height={40} />
          </div>
          <div className="flex items-center justify-between mt-2 pt-2 border-t border-[#171717]">
            <span className="text-[9px] text-zinc-700">
              {evaluated.length} evaluerte kuponger
            </span>
            <span className="text-[9px] text-zinc-700">→ nyeste</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Inline summary bar (replaces StatCards) ──────────────────────────────────

function InlineSummaryBar({ coupons }: { coupons: HistoryCouponItem[] }) {
  if (coupons.length === 0) return null;
  const evaluated = coupons.filter((c) => c.hit_rate != null);
  const best = evaluated.reduce<HistoryCouponItem | null>((acc, c) => {
    if (!acc || (c.correct_picks ?? 0) > (acc.correct_picks ?? 0)) return c;
    return acc;
  }, null);
  const mostRecent = [...coupons].sort(
    (a, b) => new Date(b.deadline_utc).getTime() - new Date(a.deadline_utc).getTime(),
  )[0];
  const recentLabel = mostRecent
    ? `${DAY_LABEL[mostRecent.day_type ?? ""] ?? ""} ${formatDeadline(mostRecent.deadline_utc)}`
        .trim()
    : null;

  const items: Array<{ label: string; value: string; accent?: boolean }> = [
    { label: "Lagret", value: String(coupons.length) },
    { label: "Evaluert", value: String(evaluated.length) },
    ...(best
      ? [{ label: "Beste", value: `${best.correct_picks}/12`, accent: true }]
      : []),
    ...(recentLabel ? [{ label: "Sist", value: recentLabel }] : []),
  ];

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 mt-2">
      {items.map((item, i) => (
        <Fragment key={item.label}>
          {i > 0 && <span className="text-zinc-800 select-none">·</span>}
          <span className="text-[12px] text-zinc-600">
            {item.label}:{" "}
            <span
              className={
                item.accent
                  ? `font-bold ${hitColor(best?.correct_picks ?? null, "complete")}`
                  : "font-medium text-zinc-300"
              }
            >
              {item.value}
            </span>
          </span>
        </Fragment>
      ))}
    </div>
  );
}

// ── Per-match pick detail ─────────────────────────────────────────────────────

function PickRow({ p }: { p: HistoryPickItem }) {
  const haResult = p.result_1x2 != null;
  const covered = p.covered === 1;
  const correct = p.model_correct === 1;

  const picksStr = p.selected_outcomes.join(" / ");
  const scoreStr =
    p.home_score != null && p.away_score != null
      ? `${p.home_score}–${p.away_score}`
      : null;

  const cdsCls =
    p.cds_bucket === "high"
      ? "text-amber-400"
      : p.cds_bucket === "medium"
      ? "text-zinc-400"
      : "text-zinc-700";

  const edgeCls =
    (p.edge_pp ?? 0) > 0
      ? "text-emerald-400"
      : (p.edge_pp ?? 0) < 0
      ? "text-red-400"
      : "text-zinc-700";

  return (
    <tr className="even:bg-white/[0.012] hover:bg-white/[0.025] transition-colors">
      <Td dim className="text-zinc-700 w-8">{p.match_number}</Td>
      <Td className="whitespace-nowrap font-medium">
        {p.home_name} <span className="text-zinc-700">–</span> {p.away_name}
      </Td>
      <Td className="font-bold text-amber-400">{p.recommended_pick}</Td>
      <Td>
        {haResult ? (
          <span className={covered ? "text-emerald-400 font-bold" : "text-red-400"}>
            {picksStr}
          </span>
        ) : (
          <span className="text-zinc-600">{picksStr}</span>
        )}
      </Td>
      <Td right className="text-zinc-600">{pct(p.confidence, 0)}</Td>
      <Td right>
        {haResult ? (
          <span className={covered ? "text-emerald-400 font-bold" : "text-red-400"}>
            {p.result_1x2}
            {covered && !correct && <span className="text-[9px] text-zinc-600 ml-1">≠tip</span>}
          </span>
        ) : (
          <span className="text-zinc-700">—</span>
        )}
      </Td>
      <Td right dim>{scoreStr ?? "—"}</Td>
      <Td right>
        {!haResult ? (
          <span className="text-zinc-700">—</span>
        ) : covered ? (
          <span className="text-emerald-400 text-sm">✓</span>
        ) : (
          <span className="text-red-400 text-sm">✗</span>
        )}
      </Td>
      <Td right className={cdsCls}>
        {p.cds != null ? `${p.cds.toFixed(1)}pp` : "—"}
      </Td>
      <Td right className={edgeCls}>
        {p.edge_pp != null ? `${p.edge_pp > 0 ? "+" : ""}${p.edge_pp.toFixed(1)}pp` : "—"}
      </Td>
    </tr>
  );
}

function CouponPicksTable({ couponId }: { couponId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["history-detail", couponId],
    queryFn: () => getHistoryCoupon(couponId),
    staleTime: 5 * 60_000,
  });

  if (isLoading) {
    return (
      <div className="py-4 text-center text-[11px] text-zinc-700 animate-pulse">
        Laster picks…
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="py-4 text-center text-[11px] text-red-500">
        Kunne ikke laste kupongen.
      </div>
    );
  }

  const ev = data.n_matches_evaluated ?? 0;
  const total = data.total_fixtures;
  const allCorrect = data.correct_picks === total && total > 0;

  return (
    <div className="border-t border-[#202020] bg-[#0a0a0a]">
      <div className="flex items-center gap-6 px-4 py-3 border-b border-[#171717]">
        <div>
          <span className="text-[9px] uppercase tracking-widest text-zinc-700 mr-2">Treff</span>
          <span className="text-zinc-200 font-bold text-sm">{fracs(data.correct_picks, ev || null)}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-widest text-zinc-700 mr-2">Treff%</span>
          <span className="text-zinc-200 font-bold text-sm">{pct(data.hit_rate)}</span>
        </div>
        <div>
          <span className="text-[9px] uppercase tracking-widest text-zinc-700 mr-2">12/12</span>
          <span className={`font-bold text-sm ${allCorrect ? "text-emerald-400" : "text-zinc-700"}`}>
            {ev >= total && total > 0 ? (allCorrect ? "Ja ✓" : "Nei") : "—"}
          </span>
        </div>
        {data.actual_payout_nok != null && (
          <div>
            <span className="text-[9px] uppercase tracking-widest text-zinc-700 mr-2">Utdeling</span>
            <span className="text-amber-400 font-bold text-sm">{nok(data.actual_payout_nok)}</span>
          </div>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>Kamp</Th>
              <Th>Tips</Th>
              <Th>Systemvalg</Th>
              <Th right>Konf.</Th>
              <Th right>Resultat</Th>
              <Th right>Score</Th>
              <Th right>Dekket</Th>
              <Th right>CDS</Th>
              <Th right>Edge</Th>
            </tr>
          </thead>
          <tbody>
            {data.picks.map((p) => (
              <PickRow key={p.match_number} p={p} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Main coupon list ──────────────────────────────────────────────────────────

function coverageLabel(n: number | null, total: number): string {
  if (n == null) return "—";
  return `${n}/${total}`;
}

function CouponRow({
  c,
  expanded,
  onToggle,
}: {
  c: HistoryCouponItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const dayLabel = DAY_LABEL[c.day_type ?? ""] ?? c.label;
  const n = c.n_matches_evaluated ?? 0;
  const total = c.total_fixtures;

  return (
    <>
      <tr
        className={`cursor-pointer transition-colors ${expanded ? "bg-[#0e0e0e]" : "hover:bg-white/[0.015]"}`}
        onClick={onToggle}
      >
        <Td>
          <span className="text-zinc-400 font-semibold">
            Uke {c.week}
          </span>
          <span className="text-zinc-700 text-[10px] ml-1">/{c.year}</span>
          <br />
          <span className="text-zinc-700 text-[10px]">{dayLabel}</span>
        </Td>
        <Td><StrategyBadge strategy={c.strategy} /></Td>
        <Td right dim>{nok(c.budget_nok)}</Td>
        <Td right dim>{c.total_rows || "—"}</Td>
        <Td right>
          {c.correct_picks != null ? (
            <span
              className={
                c.correct_picks === total
                  ? "text-emerald-400 font-bold"
                  : c.correct_picks >= total - 2
                  ? "text-amber-400 font-semibold"
                  : "text-zinc-400"
              }
            >
              {coverageLabel(c.correct_picks, total)}
            </span>
          ) : (
            <span className="text-zinc-700">—</span>
          )}
        </Td>
        <Td right>
          {c.hit_rate != null ? (
            <span className="font-semibold text-sky-400">{pct(c.hit_rate)}</span>
          ) : (
            <span className="text-zinc-700">—</span>
          )}
        </Td>
        <Td right>
          <span className="text-emerald-500">{pvr(c.pvr_at_save)}</span>
        </Td>
        <Td right dim>
          {c.p_win_at_save != null ? pct(c.p_win_at_save, 2) : "—"}
        </Td>
        <Td>
          <StatusBadge status={c.evaluation_status} />
        </Td>
        <Td right>
          <span className="text-zinc-700 text-xs select-none">{expanded ? "▲" : "▼"}</span>
        </Td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={10} className="p-0">
            <CouponPicksTable couponId={c.coupon_id} />
          </td>
        </tr>
      )}
    </>
  );
}

// ── Generation drill-down ─────────────────────────────────────────────────────

const STRAT_ORDER = ["safe", "balanced", "jackpot"] as const;
const GEN_BUDGETS = [32, 96, 192, 384];
const SHORT_LABEL: Record<string, string> = {
  safe: "Treffsikker",
  balanced: "Balansert",
  jackpot: "Risiko",
};
const STRAT_ACCENT: Record<string, string> = {
  safe: "#38bdf8",
  balanced: "#a78bfa",
  jackpot: "#F5C542",
};

// Per-coupon-type visual identity
const COUPON_IDENTITY: Record<string, {
  emoji: string; name: string; accentColor: string; borderColor: string; headerBg: string;
}> = {
  SATURDAY: {
    emoji: "🏆",
    name: "Lørdagskupongen",
    accentColor: "#C77A14",
    borderColor: "rgba(199,122,20,0.38)",
    headerBg: "linear-gradient(120deg, rgba(199,122,20,0.09) 0%, transparent 60%)",
  },
  SUNDAY: {
    emoji: "⚡",
    name: "Søndagskupongen",
    accentColor: "#0EA5E9",
    borderColor: "rgba(14,165,233,0.30)",
    headerBg: "linear-gradient(120deg, rgba(14,165,233,0.08) 0%, transparent 60%)",
  },
  MIDWEEK: {
    emoji: "🔥",
    name: "Midtukekupongen",
    accentColor: "#8B5CF6",
    borderColor: "rgba(139,92,246,0.32)",
    headerBg: "linear-gradient(120deg, rgba(139,92,246,0.09) 0%, transparent 60%)",
  },
};
const DEFAULT_IDENTITY = {
  emoji: "🎯",
  name: "Kupong",
  accentColor: "#F5C542",
  borderColor: "rgba(245,197,66,0.25)",
  headerBg: "linear-gradient(120deg, rgba(245,197,66,0.07) 0%, transparent 60%)",
};

const BUDGET_PRODUCT: Record<number, string> = {
  32: "Minimal",
  96: "Moderat",
  192: "Anbefalt",
  384: "Aggressiv",
};

function daysUntil(deadlineUtc: string): string {
  const diff = new Date(deadlineUtc).getTime() - Date.now();
  if (diff <= 0) return "Utgått";
  const d = Math.floor(diff / 86_400_000);
  const h = Math.floor((diff % 86_400_000) / 3_600_000);
  if (d === 0) return `${h}t igjen`;
  if (d === 1) return "I morgen";
  return `${d} dager`;
}

function hitColor(n: number | null, status: string): string {
  if (n == null || status === "pending") return "text-zinc-800";
  if (n === 12) return "text-amber-400";
  if (n >= 11) return "text-emerald-300";
  if (n >= 10) return "text-emerald-400";
  if (n >= 9) return "text-emerald-500";
  if (n >= 8) return "text-zinc-300";
  return "text-zinc-500";
}

function hitBgClass(n: number | null, status: string): string {
  if (n == null || status === "pending") return "";
  if (n === 12) return "bg-amber-500/10";
  if (n >= 10) return "bg-emerald-500/[0.08]";
  if (n >= 9) return "bg-emerald-500/[0.05]";
  return "";
}

/** Format deadline_utc → "28. juni 2026" using local (Norwegian) date parsing */
function formatDeadline(deadlineUtc: string): string {
  const d = new Date(deadlineUtc);
  return d.toLocaleDateString("no-NO", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Human-readable coupon title derived from day_type + deadline (never the raw label) */
function couponTitle(dayType: string | null, deadlineUtc: string): string {
  const day = dayType ? (DAY_LABEL[dayType] ?? dayType) : "Kupong";
  const date = formatDeadline(deadlineUtc);
  return `${day} · ${date}`;
}

function PickPill({ signs, result }: { signs: string[]; result: string | null }) {
  return (
    <span className="inline-flex items-center gap-[3px]">
      {signs.map((s) => {
        const isWinner = result != null && s === result;
        return (
          <span
            key={s}
            className={
              isWinner
                ? "px-1.5 py-[2px] rounded text-[11px] font-black bg-emerald-500/20 text-emerald-400 border border-emerald-500/50"
                : "px-1.5 py-[2px] rounded text-[11px] font-black bg-[#181818] text-zinc-600 border border-zinc-800/80"
            }
          >
            {s}
          </span>
        );
      })}
      {/* Actual result shown as red pill when not covered */}
      {result != null && !signs.includes(result) && (
        <span className="ml-1 px-1.5 py-[2px] rounded text-[11px] font-black bg-red-500/10 text-red-400 border border-red-500/30">
          {result}
        </span>
      )}
    </span>
  );
}

function GenerationDetailPanel({ generationId }: { generationId: string }) {
  const { data, isLoading } = useQuery<GenerationDetail>({
    queryKey: ["gen-detail", generationId],
    queryFn: () => getGenerationDetail(generationId),
    staleTime: 10 * 60_000,
    enabled: !!generationId,
  });

  if (isLoading) {
    return (
      <div className="mt-3 rounded-lg border border-[#202020] bg-[#0d0d0d] py-8 text-center">
        <div className="flex items-center justify-center gap-2 text-zinc-700">
          <span className="text-[11px] animate-pulse">Laster kamprapport…</span>
        </div>
      </div>
    );
  }
  if (!data) return null;

  const coveredCount = data.picks.filter((p) => p.covered === true).length;
  const missedCount = data.picks.filter((p) => p.covered === false).length;
  const nEval = data.picks.filter((p) => p.result_1x2 != null).length;
  const isPending = data.evaluation_status === "pending";

  return (
    <div className="mt-3 rounded-lg border border-[#1e1e1e] bg-[#080808] overflow-hidden">
      {/* Detail header — match report style */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#161616] bg-[#0c0c0c]">
        <div className="flex items-center gap-3">
          <StrategyBadge strategy={data.strategy} />
          <span className="text-[11px] text-zinc-500 tabular-nums">
            {Math.round(data.budget)} kr · {data.row_count} rekker
          </span>
          {data.pvr != null && (
            <span className="text-[10px] text-emerald-600 tabular-nums font-medium">{pvr(data.pvr)} PVR</span>
          )}
        </div>
        {!isPending && nEval > 0 && (
          <div className="flex items-center gap-3 text-[11px] tabular-nums">
            <span className="text-emerald-400 font-bold">{coveredCount} dekket</span>
            <span className="text-zinc-700">·</span>
            <span className="text-red-400 font-bold">{missedCount} bom</span>
          </div>
        )}
        {isPending && (
          <span className="text-[10px] text-zinc-700">Ikke spilt ennå</span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr className="border-b border-[#1e1e1e]">
              <th className="w-10 px-4 py-2.5 text-[10px] font-semibold text-zinc-700 text-left">#</th>
              <th className="px-4 py-2.5 text-[10px] font-semibold text-zinc-700 text-left">Kamp</th>
              <th className="px-4 py-2.5 text-[10px] font-semibold text-zinc-700 text-left">Valg</th>
              <th className="px-4 py-2.5 text-[10px] font-semibold text-zinc-700 text-right">Score</th>
              <th className="px-4 py-2.5 text-[10px] font-semibold text-zinc-700 text-right">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.picks.map((p) => {
              const hasResult = p.result_1x2 != null;
              const covered = p.covered === true;
              const missed = hasResult && !covered;
              const scoreStr =
                p.home_score != null && p.away_score != null
                  ? `${p.home_score}–${p.away_score}`
                  : null;
              return (
                <tr
                  key={p.match_number}
                  className={[
                    "border-b border-[#161616] transition-colors",
                    covered
                      ? "bg-emerald-950/[0.22] hover:bg-emerald-950/[0.32]"
                      : missed
                      ? "bg-red-950/[0.20] hover:bg-red-950/[0.30]"
                      : "hover:bg-white/[0.015]",
                  ].join(" ")}
                >
                  <td className="px-4 py-3 text-[11px] text-zinc-700 tabular-nums">{p.match_number}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-[12px] font-medium text-zinc-300">{p.home_name}</span>
                    <span className="text-zinc-700 mx-2 text-[11px]">–</span>
                    <span className="text-[12px] font-medium text-zinc-300">{p.away_name}</span>
                  </td>
                  <td className="px-4 py-3">
                    <PickPill signs={p.selected_outcomes} result={p.result_1x2} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {scoreStr ? (
                      <span className="text-[12px] text-zinc-400 tabular-nums font-semibold">{scoreStr}</span>
                    ) : (
                      <span className="text-[11px] text-zinc-800">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {!hasResult ? (
                      <span className="text-[11px] text-zinc-800">—</span>
                    ) : covered ? (
                      <span className="text-[12px] font-bold text-emerald-400">✓ Dekket</span>
                    ) : (
                      <span className="text-[12px] font-bold text-red-400">✕ Bom</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type CouponGroup = {
  coupon_id: string;
  coupon_label: string;
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
      const entry: CouponGroup = {
        coupon_id: g.coupon_id,
        coupon_label: g.coupon_label,
        week: g.week,
        year: g.year,
        day_type: g.day_type,
        deadline_utc: g.deadline_utc,
        generations: [],
      };
      seen.set(g.coupon_id, entry);
      result.push(entry);
    }
    seen.get(g.coupon_id)!.generations.push(g);
  }
  return result;
}

type StratSummary = {
  strategy: string;
  min: number | null;
  max: number | null;
  bestBudget: number | null;
  budgetScores: { budget: number; score: number | null }[];
  allSame: boolean;
  anyEvaluated: boolean;
};

function summarizeStrategies(
  byStratBudget: Map<string, Map<number, GenerationSummary>>
): StratSummary[] {
  return STRAT_ORDER.map((strategy) => {
    const budgetMap = byStratBudget.get(strategy);
    const budgetScores = GEN_BUDGETS.map((b) => ({
      budget: b,
      score: budgetMap?.get(b)?.correct_picks ?? null,
    }));
    const evaluated = budgetScores.filter((s) => s.score != null);
    if (!evaluated.length) {
      return { strategy, min: null, max: null, bestBudget: null, budgetScores, allSame: true, anyEvaluated: false };
    }
    const scores = evaluated.map((s) => s.score as number);
    const min = Math.min(...scores);
    const max = Math.max(...scores);
    const bestBudget = evaluated.find((s) => s.score === max)?.budget ?? null;
    return { strategy, min, max, bestBudget, budgetScores, allSame: min === max, anyEvaluated: true };
  });
}

function CouponGenerationGroup({
  group,
  defaultExpanded,
}: {
  group: CouponGroup;
  defaultExpanded: boolean;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const [viewingGenId, setViewingGenId] = useState<string | null>(null);

  const identity =
    group.day_type ? (COUPON_IDENTITY[group.day_type] ?? DEFAULT_IDENTITY) : DEFAULT_IDENTITY;

  const byStratBudget = new Map<string, Map<number, GenerationSummary>>();
  for (const g of group.generations) {
    if (!byStratBudget.has(g.strategy)) byStratBudget.set(g.strategy, new Map());
    byStratBudget.get(g.strategy)!.set(Math.round(g.budget), g);
  }

  const nEvaluated = group.generations.filter((g) => g.evaluation_status === "complete").length;
  const isEvaluated = nEvaluated > 0;

  // Best generation: highest correct_picks among evaluated
  const evaledGens = group.generations.filter((g) => g.correct_picks != null);
  const bestGen = evaledGens.reduce<GenerationSummary | null>((best, g) => {
    if (!best || (g.correct_picks ?? 0) > (best.correct_picks ?? 0)) return g;
    return best;
  }, null);

  const stratSummaries = summarizeStrategies(byStratBudget);
  const allBudgetsUniform = stratSummaries.filter((s) => s.anyEvaluated).every((s) => s.allSame);
  const activeGenId = expanded ? (viewingGenId ?? bestGen?.generation_id ?? null) : null;
  const activeStrategy = group.generations.find((g) => g.generation_id === activeGenId)?.strategy ?? null;

  if (!isEvaluated) {
    // ── PENDING CARD ──────────────────────────────────────────────────────────
    const countdown = daysUntil(group.deadline_utc);
    const deadlineTime = new Date(group.deadline_utc).toLocaleTimeString("no-NO", {
      hour: "2-digit",
      minute: "2-digit",
    });
    return (
      <div
        className="rounded-xl overflow-hidden bg-[#090909] border border-[#1c1c1c]"
        style={{ borderTopWidth: "2px", borderTopColor: identity.borderColor }}
      >
        <button
          className="w-full text-left hover:bg-white/[0.012] transition-colors"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <div className="px-5 py-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[15px] leading-none">{identity.emoji}</span>
                  <span
                    className="text-[13px] font-black tracking-tight"
                    style={{ color: identity.accentColor, opacity: 0.65 }}
                  >
                    {identity.name}
                  </span>
                </div>
                <div className="text-[11px] text-zinc-700 ml-[23px]">
                  {formatDeadline(group.deadline_utc)}
                  <span className="text-zinc-800 mx-1.5">·</span>
                  Uke {group.week}
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span
                  className="inline-flex items-center h-5 px-2.5 rounded border text-[9px] font-bold tracking-wide"
                  style={{
                    borderColor: identity.borderColor,
                    color: identity.accentColor,
                    opacity: 0.55,
                  }}
                >
                  Kommende
                </span>
                <span className="text-zinc-800 text-[10px] select-none">{expanded ? "▲" : "▼"}</span>
              </div>
            </div>
            <div className="mt-3 ml-[23px] flex items-center gap-3 flex-wrap">
              <span
                className="text-[20px] font-black tabular-nums"
                style={{ color: identity.accentColor, opacity: 0.5 }}
              >
                {countdown}
              </span>
              <span className="text-[10px] text-zinc-800">· Frist {deadlineTime}</span>
              <span className="text-[10px] text-zinc-800 border-l border-[#1e1e1e] pl-3">
                {group.generations.length} generasjoner klar
              </span>
            </div>
          </div>
        </button>

        {expanded && (
          <div className="border-t border-[#141414] px-5 py-4 overflow-x-auto">
            <table className="w-full border-collapse" style={{ minWidth: 360 }}>
              <thead>
                <tr>
                  <th className="text-left pr-4 pb-3 w-32" />
                  {GEN_BUDGETS.map((b) => (
                    <th key={b} className="text-center pb-3" style={{ minWidth: 80 }}>
                      <div className="text-[10px] font-semibold text-zinc-800">
                        {BUDGET_PRODUCT[b] ?? `${b} kr`}
                      </div>
                      <div className="text-[9px] text-zinc-900 tabular-nums mt-0.5">{b} kr</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {STRAT_ORDER.map((strategy) => (
                  <tr key={strategy}>
                    <td
                      className="pr-4 py-2.5 text-[11px] font-black whitespace-nowrap opacity-20"
                      style={{ color: STRAT_ACCENT[strategy] }}
                    >
                      {SHORT_LABEL[strategy]}
                    </td>
                    {GEN_BUDGETS.map((budget) => (
                      <td key={budget} className="py-2.5 text-center">
                        <div className="inline-flex items-center justify-center rounded-lg border border-[#1a1a1a] px-3 py-2.5 min-w-[68px]">
                          <span className="text-[13px] text-zinc-900">—</span>
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  // ── EVALUATED CARD ────────────────────────────────────────────────────────
  return (
    <div
      className="rounded-xl overflow-hidden bg-[#0b0b0b] border-2"
      style={{ borderColor: identity.borderColor }}
    >
      {/* Hero header */}
      <button
        className="w-full text-left hover:bg-white/[0.015] transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
      >
        <div className="px-6 pt-5 pb-5" style={{ background: identity.headerBg }}>
          {/* Identity + status row */}
          <div className="flex items-start justify-between mb-4">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="text-[18px] leading-none">{identity.emoji}</span>
                <span
                  className="text-[14px] font-black tracking-tight uppercase"
                  style={{ color: identity.accentColor }}
                >
                  {identity.name}
                </span>
              </div>
              <div className="text-[11px] text-zinc-500 mt-1 ml-[26px]">
                {formatDeadline(group.deadline_utc)}
                <span className="text-zinc-700 mx-2">·</span>
                Uke {group.week}
              </div>
            </div>
            <div className="flex items-center gap-2.5 shrink-0">
              <span
                className="inline-flex items-center h-5 px-2.5 rounded-full text-[9px] font-bold tracking-wide border"
                style={{
                  borderColor: identity.borderColor,
                  color: identity.accentColor,
                  background: `${identity.accentColor}14`,
                }}
              >
                Evaluert
              </span>
              <span className="text-zinc-700 text-[10px] select-none">{expanded ? "▲" : "▼"}</span>
            </div>
          </div>

          {/* Hero score */}
          {bestGen && (
            <div className="ml-[26px] flex items-end gap-3">
              <div className="flex items-baseline gap-1">
                <span
                  className={`text-[60px] font-black tabular-nums leading-none ${hitColor(bestGen.correct_picks, "complete")}`}
                >
                  {bestGen.correct_picks}
                </span>
                <span className="text-[22px] font-bold text-zinc-700 tabular-nums leading-none mb-2">
                  /12
                </span>
              </div>
              <div className="pb-2">
                <div className="text-[11px] font-bold text-zinc-400 uppercase tracking-widest leading-none">
                  Treff
                </div>
                <div className="text-[11px] text-zinc-600 mt-1 leading-none">
                  {SHORT_LABEL[bestGen.strategy] ?? bestGen.strategy}
                  {" · "}
                  {BUDGET_PRODUCT[Math.round(bestGen.budget)] ?? `${Math.round(bestGen.budget)} kr`}
                </div>
              </div>
            </div>
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-[#1c1c1c]">
          {/* Strategy comparison — one row per strategy, compressed */}
          <div className="px-6 pt-4 pb-3">
            {stratSummaries.map((s) => {
              if (!s.anyEvaluated) return null;

              const bestForStrat = GEN_BUDGETS.reduce<GenerationSummary | null>((best, b) => {
                const gen = byStratBudget.get(s.strategy)?.get(b);
                if (!gen || gen.correct_picks == null) return best;
                if (!best || (gen.correct_picks ?? 0) > (best.correct_picks ?? 0)) return gen;
                return best;
              }, null);

              const isActive = activeStrategy === s.strategy;

              return (
                <button
                  key={s.strategy}
                  className={[
                    "w-full flex items-center justify-between py-2.5 px-3 -mx-3 rounded-lg transition-colors",
                    isActive ? "bg-white/[0.04]" : "hover:bg-white/[0.02]",
                  ].join(" ")}
                  onClick={() => {
                    if (bestForStrat) setViewingGenId(bestForStrat.generation_id);
                  }}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="text-[12px] font-black"
                      style={{ color: STRAT_ACCENT[s.strategy] }}
                    >
                      {SHORT_LABEL[s.strategy]}
                    </span>
                    {!s.allSame && (
                      <div className="flex items-center gap-1 text-[10px] tabular-nums text-zinc-700">
                        {s.budgetScores.map(({ budget, score }, i) => (
                          <Fragment key={budget}>
                            {i > 0 && <span className="text-zinc-800">·</span>}
                            <span
                              className={
                                score === s.max && score != null ? "text-zinc-400" : ""
                              }
                            >
                              {score ?? "—"}
                            </span>
                          </Fragment>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-2.5">
                    <span
                      className={`text-[15px] font-black tabular-nums ${hitColor(s.max, "complete")}`}
                    >
                      {s.allSame ? `${s.max}/12` : `${s.min}–${s.max}/12`}
                    </span>
                    {!s.allSame && s.bestBudget != null && (
                      <span className="text-[9px] text-zinc-600 font-semibold">
                        {BUDGET_PRODUCT[s.bestBudget] ?? `${s.bestBudget} kr`}
                      </span>
                    )}
                    <span
                      className={`text-[9px] w-3 text-center leading-none ${
                        isActive ? "text-zinc-400" : "text-zinc-900"
                      }`}
                    >
                      ▶
                    </span>
                  </div>
                </button>
              );
            })}
            {allBudgetsUniform && (
              <p className="text-[10px] text-zinc-700 mt-2 px-3">
                Budsjett hadde ingen innvirkning
              </p>
            )}
          </div>

          {/* Match breakdown — auto-loaded, no click required */}
          {activeGenId && (
            <div className="border-t border-[#181818] px-6 pb-5 pt-1">
              <GenerationDetailPanel generationId={activeGenId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function GenerationsSection({ data }: { data: GenerationSummary[] }) {
  const groups = groupByCoupon(data);

  if (groups.length === 0) {
    return (
      <div className="rounded-xl border border-[#181818] bg-[#090909] px-6 py-10 text-center">
        <p className="text-zinc-600 text-sm">Ingen frosne generasjoner ennå.</p>
        <p className="text-zinc-700 text-[11px] mt-1">
          Generasjoner fryses automatisk ved kupongfrist.
        </p>
      </div>
    );
  }

  // Sort each bucket by deadline descending — most recent first
  const byDeadlineDesc = (a: CouponGroup, b: CouponGroup) =>
    new Date(b.deadline_utc).getTime() - new Date(a.deadline_utc).getTime();

  const evaluatedGroups = groups
    .filter((g) => g.generations.some((gen) => gen.evaluation_status === "complete"))
    .sort(byDeadlineDesc);

  const pendingGroups = groups
    .filter((g) => g.generations.every((gen) => gen.evaluation_status === "pending"))
    .sort(byDeadlineDesc);

  return (
    <div>
      {/* Evaluated results — primary content */}
      {evaluatedGroups.length > 0 && (
        <div className="space-y-4">
          {evaluatedGroups.map((group) => (
            <CouponGenerationGroup
              key={group.coupon_id}
              group={group}
              defaultExpanded
            />
          ))}
        </div>
      )}

      {/* Pending coupons — quiet, separated, collapsed */}
      {pendingGroups.length > 0 && (
        <div className={evaluatedGroups.length > 0 ? "mt-8" : ""}>
          {evaluatedGroups.length > 0 && (
            <div className="flex items-center gap-4 mb-3">
              <div className="flex-1 h-px bg-[#181818]" />
              <span className="text-[10px] font-medium text-zinc-700 tracking-widest uppercase">
                Kommende
              </span>
              <div className="flex-1 h-px bg-[#181818]" />
            </div>
          )}
          <div className="space-y-2">
            {pendingGroups.map((group) => (
              <CouponGenerationGroup
                key={group.coupon_id}
                group={group}
                defaultExpanded={false}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Phase 9 — Generation analytics ───────────────────────────────────────────

const STRATEGY_CONFIGS = [
  { key: "safe",     label: "Treffsikker", accent: "#38bdf8", borderCls: "border-sky-900/30" },
  { key: "balanced", label: "Anbefalt",    accent: "#a78bfa", borderCls: "border-violet-900/30" },
  { key: "jackpot",  label: "Risiko",      accent: "#F5C542", borderCls: "border-amber-900/30" },
] as const;

function GenStratCard({ cfg, data }: {
  cfg: typeof STRATEGY_CONFIGS[number];
  data: GenerationAnalytics | undefined;
}) {
  const n_total     = data?.n_total ?? 0;
  const n_evaluated = data?.n_evaluated ?? 0;
  const enough      = n_evaluated >= 5;

  function hr(v: number | null | undefined) {
    if (!enough || v == null) return "—";
    return `${v.toFixed(0)}%`;
  }

  const roiPct = data?.roi != null ? data.roi * 100 : null;
  const roiStr = !enough || roiPct == null ? "—" : `${roiPct >= 0 ? "+" : ""}${roiPct.toFixed(1)}%`;
  const roiColor = roiPct == null ? "#3f3f46" : roiPct >= 0 ? "#34d399" : "#f87171";

  return (
    <div
      className={`rounded-xl border bg-[#101010] p-4 ${cfg.borderCls}`}
      style={{ borderColor: `${cfg.accent}18` }}
    >
      <div className="flex items-center justify-between mb-4">
        <span
          className="text-[11px] font-black tracking-[1.4px] uppercase"
          style={{ color: cfg.accent }}
        >
          {cfg.label}
        </span>
        <span className="text-[10px] text-zinc-700 tabular-nums">
          {n_total} lagret · {n_evaluated} eval.
        </span>
      </div>

      {n_total === 0 ? (
        <p className="text-[11px] text-zinc-700 py-2">Ingen data ennå.</p>
      ) : (
        <div className="space-y-3">
          {/* Hit rates grid */}
          <div className="grid grid-cols-4 gap-2">
            {([
              { label: "9+",    v: hr(data?.hit_rate_9) },
              { label: "10+",   v: hr(data?.hit_rate_10) },
              { label: "11+",   v: hr(data?.hit_rate_11) },
              { label: "12/12", v: hr(data?.hit_rate_12) },
            ]).map((r) => (
              <div key={r.label} className="text-center">
                <div className="text-[8px] uppercase tracking-wider text-zinc-700 mb-1">{r.label}</div>
                <div
                  className="text-[13px] font-bold tabular-nums"
                  style={{ color: r.v === "—" ? "#3f3f46" : cfg.accent }}
                >
                  {r.v}
                </div>
              </div>
            ))}
          </div>

          <div className="h-px bg-[#1a1a1a]" />

          {/* Secondary stats */}
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-[8px] uppercase tracking-wider text-zinc-700 mb-1">Snitt treff</div>
              <div className="text-[12px] font-bold text-zinc-300 tabular-nums">
                {data?.avg_hits != null ? data.avg_hits.toFixed(1) : "—"}
              </div>
            </div>
            <div>
              <div className="text-[8px] uppercase tracking-wider text-zinc-700 mb-1">Snitt PVR</div>
              <div className="text-[12px] font-bold text-emerald-400 tabular-nums">
                {data?.avg_pvr != null ? `${data.avg_pvr.toFixed(2)}×` : "—"}
              </div>
            </div>
            <div>
              <div className="text-[8px] uppercase tracking-wider text-zinc-700 mb-1">ROI</div>
              <div className="text-[12px] font-bold tabular-nums" style={{ color: roiColor }}>
                {roiStr}
              </div>
            </div>
          </div>

          {!enough && n_evaluated > 0 && (
            <p className="text-[9px] text-zinc-800 text-center">
              Trenger 5 evaluerte for treff-statistikk
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function GenerationAnalyticsSection({ data }: { data: GenerationAnalytics[] }) {
  const byStrategy = Object.fromEntries(data.map((d) => [d.strategy, d]));
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {STRATEGY_CONFIGS.map((cfg) => (
        <GenStratCard key={cfg.key} cfg={cfg} data={byStrategy[cfg.key]} />
      ))}
    </div>
  );
}

// ── Strategy performance ──────────────────────────────────────────────────────

function StrategySection({ data }: { data: StrategyPerformance[] }) {
  if (data.length === 0) {
    return (
      <p className="text-[11px] text-zinc-600 py-2">
        Ingen strategi-data ennå. Kjør{" "}
        <code className="text-zinc-500">python evaluate.py --all</code> etter at resultater er lagt inn.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Th>Strategi</Th>
            <Th right>Kuponger</Th>
            <Th right>Treff%</Th>
            <Th right>NT-treff%</Th>
            <Th right>Snitt PVR</Th>
            <Th right>P(12/12)</Th>
            <Th right>Jackpot</Th>
          </tr>
        </thead>
        <tbody>
          {data.map((s) => (
            <tr key={s.strategy} className="even:bg-white/[0.012]">
              <Td><StrategyBadge strategy={s.strategy} /></Td>
              <Td right dim>{s.n_coupons}</Td>
              <Td right className="font-semibold text-sky-400">{pct(s.avg_hit_rate)}</Td>
              <Td right className="text-amber-400/80">{pct(s.avg_nt_hit_rate)}</Td>
              <Td right className="text-emerald-400">{pvr(s.avg_pvr)}</Td>
              <Td right dim>{pct(s.avg_p_win, 2)}</Td>
              <Td right>{s.n_jackpots > 0 ? <span className="text-amber-400 font-bold">{s.n_jackpots}</span> : <span className="text-zinc-700">0</span>}</Td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-[9px] text-zinc-800 mt-2 px-1">
        Treff% = andel kamper der kupongutvalget dekket det faktiske resultatet. NT-treff% = NT-folkets topptips-nøyaktighet.
      </p>
    </div>
  );
}

// ── CDS validation ────────────────────────────────────────────────────────────

const CDS_BUCKET_LABEL: Record<string, string> = {
  high: "Sterk ≥10pp",
  medium: "Moderat 5–10pp",
  low: "Lav <5pp",
};

function CdsSection({ data }: { data: CdsValidationBucket[] }) {
  const total = data.reduce((s, r) => s + r.n, 0);
  if (total < 3) {
    return (
      <p className="text-[11px] text-zinc-600 py-2">
        Ikke nok data ennå. Krever kuponger med lagret CDS-snapshotdata og tilhørende resultater.
      </p>
    );
  }

  const totalModel = data.reduce((s, r) => s + r.n_model, 0);
  const totalNt = data.reduce((s, r) => s + (r.n_nt ?? 0), 0);
  const hasNt = data.some((r) => r.n_nt != null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Th>CDS-nivå</Th>
            <Th right>Kamper</Th>
            <Th right>Modell-treff</Th>
            <Th right>NT-treff</Th>
            <Th right>Diff</Th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => {
            const modelPct = row.n > 0 ? (row.n_model / row.n) * 100 : 0;
            const ntPct = row.n_nt != null && row.n > 0 ? (row.n_nt / row.n) * 100 : null;
            const diff = ntPct != null ? modelPct - ntPct : null;
            const diffCls = diff == null ? "" : diff > 0 ? "text-emerald-400 font-bold" : "text-red-400 font-bold";
            return (
              <tr key={row.cds_bucket} className="even:bg-white/[0.012]">
                <Td>{CDS_BUCKET_LABEL[row.cds_bucket] ?? row.cds_bucket}</Td>
                <Td right dim>{row.n}</Td>
                <Td right className="font-semibold text-sky-400">{`${modelPct.toFixed(0)}%`}</Td>
                <Td right className="text-amber-400/80">{ntPct != null ? `${ntPct.toFixed(0)}%` : "—"}</Td>
                <Td right className={diffCls}>
                  {diff != null ? `${diff > 0 ? "+" : ""}${diff.toFixed(1)}pp` : "—"}
                </Td>
              </tr>
            );
          })}
          <tr className="border-t border-[#202020]">
            <Td className="font-bold">Totalt</Td>
            <Td right className="font-bold text-zinc-200">{total}</Td>
            <Td right className="font-bold text-sky-400">
              {total > 0 ? `${((totalModel / total) * 100).toFixed(0)}%` : "—"}
            </Td>
            <Td right className="font-bold text-amber-400/80">
              {hasNt && total > 0 ? `${((totalNt / total) * 100).toFixed(0)}%` : "—"}
            </Td>
            <Td right>
              {hasNt && total > 0 ? (
                <span className={((totalModel - totalNt) / total) * 100 > 0 ? "text-emerald-400 font-bold" : "text-red-400 font-bold"}>
                  {`${(((totalModel - totalNt) / total) * 100) > 0 ? "+" : ""}${(((totalModel - totalNt) / total) * 100).toFixed(1)}pp`}
                </span>
              ) : "—"}
            </Td>
          </tr>
        </tbody>
      </table>
      <p className="text-[9px] text-zinc-800 mt-2 px-1">
        CDS = crowd disagreement score fryst ved lagringstidspunkt. Diff = modellfordel vs NT-folket i pp.
      </p>
    </div>
  );
}

// ── Model vs NT ───────────────────────────────────────────────────────────────

function NtSection({ data }: { data: NtComparison | null }) {
  if (!data || data.n_total < 3) {
    return (
      <p className="text-[11px] text-zinc-600 py-2">
        Ikke nok data ennå. Krever kuponger med lagret pub_prob-snapshotdata og tilhørende resultater.
      </p>
    );
  }
  const modelPct = (data.n_model / data.n_total) * 100;
  const ntPct = (data.n_nt / data.n_total) * 100;
  const diff = modelPct - ntPct;
  const diffCls = diff > 0 ? "text-emerald-400" : "text-red-400";

  const cards = [
    { label: "Kamper evaluert", value: String(data.n_total), cls: "text-zinc-100" },
    { label: "Modell-treff", value: `${modelPct.toFixed(1)}%`, cls: "text-sky-400" },
    { label: "NT-tips-treff", value: `${ntPct.toFixed(1)}%`, cls: "text-amber-400" },
    { label: "Modell-fordel", value: `${diff > 0 ? "+" : ""}${diff.toFixed(1)}pp`, cls: diffCls },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="rounded-xl border border-[#202020] bg-[#101010] px-4 py-3">
          <div className="text-[9px] font-bold uppercase tracking-[1.4px] text-zinc-700 mb-1">{c.label}</div>
          <div className={`text-xl font-black tracking-tight ${c.cls}`}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}

// ── Top navigation ────────────────────────────────────────────────────────────

function TopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-[#202020]">
      <div className="absolute inset-0 bg-[#050505]/95 backdrop-blur-md" />
      <div className="relative max-w-screen-xl mx-auto px-4 sm:px-6 flex items-center gap-3" style={{ height: 52 }}>
        {/*
          Logo zone — reserved for future cow + football SVG mark.
          36×36px, rounded-xl. Replace with <img src="/logo.svg"> when ready.
        */}
        <div className="rounded-xl border border-[#282828] overflow-hidden shrink-0">
          <LogoMark size={36} />
        </div>

        <span className="text-[17px] font-black tracking-tight select-none">
          <span className="text-zinc-100">Tippe</span>
          <span className="text-amber-400">Q</span>
          <span className="text-zinc-100">pongen</span>
        </span>

        <nav className="flex items-center gap-1 ml-1">
          <Link
            href="/coupon"
            className="h-7 px-3 rounded-md text-[11px] font-medium text-zinc-600 hover:text-zinc-300 hover:bg-white/[0.04] transition-colors flex items-center"
          >
            Kupong
          </Link>
          <div className="h-7 px-3 rounded-md text-[11px] font-medium text-zinc-200 bg-[#151515] flex items-center border border-[#202020]">
            Historikk
          </div>
        </nav>
      </div>
    </header>
  );
}

// ── Section label — two-tier hierarchy ───────────────────────────────────────

function PrimarySection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-10">
      <div className="flex items-center gap-4 mb-5">
        <span className="font-display text-xl font-semibold text-zinc-200 tracking-wide uppercase">{title}</span>
        <div className="flex-1 h-px bg-[#1e1e1e]" />
      </div>
      {children}
    </div>
  );
}

function Collapsible({
  title,
  defaultOpen = true,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="mb-8">
      <button
        className="w-full flex items-center gap-3 mb-4 group"
        onClick={() => setOpen((v) => !v)}
      >
        <span className="font-display text-sm font-semibold tracking-widest uppercase text-zinc-400 group-hover:text-zinc-200 transition-colors">
          {title}
        </span>
        <div className="flex-1 h-px bg-[#1c1c1c]" />
        <span className="text-zinc-700 text-[10px] group-hover:text-zinc-500 transition-colors select-none">
          {open ? "▲" : "▼"}
        </span>
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: coupons = [], isLoading: loadingList } = useQuery({
    queryKey: ["history"],
    queryFn: getHistory,
    staleTime: 2 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  const { data: stratPerf = [] } = useQuery({
    queryKey: ["history-strategy"],
    queryFn: getHistoryStrategyPerformance,
    staleTime: 5 * 60_000,
  });

  const { data: cdsData = [] } = useQuery({
    queryKey: ["history-cds"],
    queryFn: getHistoryCdsValidation,
    staleTime: 5 * 60_000,
  });

  const { data: ntData } = useQuery({
    queryKey: ["history-nt"],
    queryFn: getHistoryNtComparison,
    staleTime: 5 * 60_000,
  });

  const { data: genAnalytics = [] } = useQuery({
    queryKey: ["analytics-strategy"],
    queryFn: getStrategyAnalytics,
    staleTime: 5 * 60_000,
    refetchInterval: 5 * 60_000,
  });

  const { data: generationsData = [] } = useQuery<GenerationSummary[]>({
    queryKey: ["analytics-generations"],
    queryFn: getGenerations,
    staleTime: 5 * 60_000,
  });

  function toggle(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

  return (
    <div className="min-h-screen" style={{ background: "#050505" }}>
      <TopBar />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-10">
        {/* Page header */}
        <div className="mb-10">
          <h1 className="font-display text-6xl font-bold tracking-tight leading-none text-[#F5C542]">
            Historikk
          </h1>
          {coupons.length > 0 && <InlineSummaryBar coupons={coupons} />}
        </div>

        {/* ── Generasjoner — PRIMARY CONTENT ───────────────────── */}
        <PrimarySection title="Generasjoner">
          {loadingList ? (
            <div className="py-12 text-center text-zinc-700 text-sm animate-pulse">
              Laster generasjoner…
            </div>
          ) : (
            <GenerationsSection data={generationsData} />
          )}
        </PrimarySection>

        {/* ── Analyse ───────────────────────────────────────────── */}
        <Collapsible title="Strategi-analyse" defaultOpen={false}>
          <GenerationAnalyticsSection data={genAnalytics} />
        </Collapsible>

        {/* ── Ytelsestrender ────────────────────────────────────── */}
        <Collapsible
          title="Ytelsestrender"
          defaultOpen={coupons.filter((c) => c.hit_rate != null).length >= 2}
        >
          <TrendCharts coupons={coupons} />
        </Collapsible>

        {/* ── Kuponger (legacy table) ───────────────────────────── */}
        <Collapsible title="Alle kuponger" defaultOpen={false}>
          {loadingList ? (
            <div className="py-8 text-center text-zinc-700 text-sm animate-pulse">
              Laster historikk…
            </div>
          ) : coupons.length === 0 ? (
            <div className="rounded-xl border border-[#1e1e1e] bg-[#0d0d0d] px-6 py-8 text-center">
              <p className="text-zinc-600 text-sm mb-2">Ingen lagrede kuponger ennå.</p>
              <p className="text-zinc-700 text-[11px]">
                Historikk fylles automatisk når kuponger fryses før frist.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-[#1e1e1e] bg-[#0d0d0d]">
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <Th>Kupong</Th>
                    <Th>Strategi</Th>
                    <Th right>Innsats</Th>
                    <Th right>Rekker</Th>
                    <Th right>Treff</Th>
                    <Th right>Treff%</Th>
                    <Th right>PVR</Th>
                    <Th right>P(12)</Th>
                    <Th>Status</Th>
                    <Th right>{""}</Th>
                  </tr>
                </thead>
                <tbody>
                  {coupons.map((c) => (
                    <CouponRow
                      key={c.coupon_id}
                      c={c}
                      expanded={expandedId === c.coupon_id}
                      onToggle={() => toggle(c.coupon_id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Collapsible>

        {/* ── Strategi-ytelse ───────────────────────────────────── */}
        <Collapsible title="Strategi-ytelse" defaultOpen={false}>
          <StrategySection data={stratPerf} />
        </Collapsible>

        {/* ── Modell vs NT ──────────────────────────────────────── */}
        <Collapsible title="Modell vs NT-folkets topptips" defaultOpen={false}>
          <NtSection data={ntData ?? null} />
        </Collapsible>

        {/* ── CDS-validering ────────────────────────────────────── */}
        <Collapsible title="CDS-validering" defaultOpen={false}>
          <CdsSection data={cdsData} />
        </Collapsible>
      </main>
    </div>
  );
}
