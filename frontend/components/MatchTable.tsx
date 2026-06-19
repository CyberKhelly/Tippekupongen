"use client";

import { cn, recValue } from "@/lib/utils";
import type { MatchResult } from "@/lib/types";

// ── Probability bar ────────────────────────────────────────────────────────────

const OUTCOME_COLORS: Record<string, string> = {
  H: "#4a80b0",
  U: "#4e6070",
  B: "#a06818",
};

function ProbBar({
  label,
  value,
  highlighted,
  delay,
}: {
  label: string;
  value: number;
  highlighted: boolean;
  delay: number;
}) {
  const pct = Math.round(value * 100);
  const color = OUTCOME_COLORS[label] ?? "#607888";
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span
        className={cn(
          "text-[10px] w-3 text-right shrink-0 tabular-nums font-medium",
          highlighted ? "text-slate-300" : "text-slate-600"
        )}
      >
        {label}
      </span>
      <div className="flex-1 h-[3px] bg-slate-800/80 rounded-full overflow-hidden min-w-[36px]">
        <div
          className="h-full rounded-full animate-bar-grow"
          style={{
            width: `${pct}%`,
            backgroundColor: highlighted ? color : color,
            opacity: highlighted ? 1 : 0.28,
            transformOrigin: "left",
            animationDelay: `${delay}ms`,
          }}
        />
      </div>
      <span
        className={cn(
          "text-[10px] tabular-nums w-6 text-right shrink-0 font-medium",
          highlighted ? "text-slate-300" : "text-slate-700"
        )}
      >
        {pct}%
      </span>
    </div>
  );
}

// ── CDS badge ────────────────────────────────────────────────────────────────

function CdsBadge({ cds }: { cds: number | null }) {
  if (cds == null)
    return <span className="text-[10px] text-slate-700">—</span>;

  const level = cds >= 20 ? "high" : cds >= 10 ? "mid" : "low";
  const cls = {
    high: "text-amber-300 bg-amber-400/[0.1] border border-amber-400/[0.2]",
    mid: "text-slate-300 bg-white/[0.05] border border-white/[0.08]",
    low: "text-slate-600",
  }[level];

  return (
    <span className={cn("text-[10px] tabular-nums font-semibold px-1.5 py-0.5 rounded-md", cls)}>
      {cds.toFixed(1)}
    </span>
  );
}

// ── VI badge ─────────────────────────────────────────────────────────────────

function ViBadge({ vi }: { vi: number | null }) {
  if (vi == null)
    return <span className="text-[10px] text-slate-700">—</span>;

  const isHigh = vi >= 1.2;
  const isAbove = vi > 1.0;
  const color = isHigh
    ? "text-emerald-400"
    : isAbove
    ? "text-slate-300"
    : "text-red-400/70";
  const arrow = isAbove ? "↑" : "↓";

  return (
    <span className={cn("text-[10px] tabular-nums font-bold", color)}>
      {vi.toFixed(2)}
      <span className="text-[8px] ml-0.5 opacity-60">{arrow}</span>
    </span>
  );
}

// ── Edge badge ────────────────────────────────────────────────────────────────

function EdgeBadge({ match }: { match: MatchResult }) {
  if (!match.has_public_tips)
    return <span className="text-[10px] text-slate-700">—</span>;
  const val = recValue(match.recommendation, match.value_h, match.value_u, match.value_b);
  if (val == null)
    return <span className="text-[10px] text-slate-700">—</span>;

  const positive = val > 0;
  return (
    <span
      className={cn(
        "text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded-md",
        positive
          ? "text-amber-300 bg-amber-400/[0.1] border border-amber-400/[0.15]"
          : "text-red-400/70 bg-red-400/[0.05] border border-red-400/[0.1]"
      )}
    >
      {positive ? "+" : ""}
      {val.toFixed(0)}pp
    </span>
  );
}

// ── Coverage ──────────────────────────────────────────────────────────────────

const COVERAGE_SYMBOL: Record<string, string> = {
  single: "",
  half_cover: "◐",
  full_cover: "●",
};
const COVERAGE_LABEL: Record<string, string> = {
  single: "Singel",
  half_cover: "Halvdekk",
  full_cover: "Heldekk",
};
const COVERAGE_COLOR: Record<string, string> = {
  single: "text-slate-600",
  half_cover: "text-amber-700/80",
  full_cover: "text-amber-500/80",
};

// ── Skeleton row ─────────────────────────────────────────────────────────────

function SkeletonRow({ i }: { i: number }) {
  return (
    <tr className="border-b border-white/[0.04]" style={{ animationDelay: `${i * 35}ms` }}>
      <td className="py-3 px-3">
        <div className="skeleton h-3 w-4 rounded" />
      </td>
      <td className="py-3 px-3">
        <div className="space-y-1.5">
          <div className="skeleton h-3 rounded" style={{ width: `${58 + (i * 19) % 28}%` }} />
          <div className="skeleton h-2.5 w-20 rounded" />
        </div>
      </td>
      {[64, 120, 110, 76, 52, 40, 40].map((w, j) => (
        <td key={j} className="py-3 px-3">
          <div className="skeleton h-3 rounded mx-auto" style={{ width: w * 0.55 }} />
        </td>
      ))}
    </tr>
  );
}

// ── Match row ────────────────────────────────────────────────────────────────

function MatchRow({ match, index }: { match: MatchResult; index: number }) {
  const isConviction = match.is_conviction;
  const picks = match.picks;
  const barDelay = index * 35;

  const crowd =
    match.has_public_tips
      ? [
          { label: "H", v: match.pub_prob_h ?? 0 },
          { label: "U", v: match.pub_prob_u ?? 0 },
          { label: "B", v: match.pub_prob_b ?? 0 },
        ]
      : null;

  return (
    <tr
      className={cn(
        "border-b border-white/[0.04] transition-colors duration-150 animate-fade-up group",
        isConviction
          ? "border-l-2 border-l-amber-400/30 hover:bg-amber-400/[0.03]"
          : "border-l-2 border-l-transparent hover:bg-white/[0.02]"
      )}
      style={{ animationDelay: `${index * 40}ms` }}
    >
      {/* # */}
      <td className="py-3 pl-4 pr-2 w-8">
        <span className="text-[10px] text-slate-700 tabular-nums font-medium">
          {match.match_number}
        </span>
      </td>

      {/* Teams */}
      <td className="py-3 px-3">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Conviction dot */}
          <span
            className={cn(
              "shrink-0 transition-opacity",
              isConviction ? "opacity-100" : "opacity-0"
            )}
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inset-0 rounded-full bg-amber-400 animate-ping opacity-40" />
              <span className="relative rounded-full h-1.5 w-1.5 bg-amber-400" />
            </span>
          </span>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold text-slate-200 truncate leading-snug">
              {match.home_team}
            </div>
            <div className="flex items-center gap-1 mt-0.5">
              <span className="text-[9px] font-semibold text-slate-600 uppercase tracking-wider">vs</span>
              <span className="text-[11px] text-slate-500 truncate">{match.away_team}</span>
            </div>
          </div>
        </div>
      </td>

      {/* Pick + coverage */}
      <td className="py-3 px-3 w-24">
        <div className="flex flex-col items-center gap-1">
          <div className="inline-flex items-center px-2 py-1 bg-amber-400/[0.07] border border-amber-400/[0.2] rounded-lg group-hover:bg-amber-400/[0.1] transition-colors">
            <span className="text-xs font-black tracking-wider text-amber-300">
              {picks.join(" · ")}
            </span>
          </div>
          <div className={cn("text-[9px] font-semibold uppercase tracking-wider", COVERAGE_COLOR[match.coverage_type])}>
            {COVERAGE_SYMBOL[match.coverage_type]
              ? `${COVERAGE_SYMBOL[match.coverage_type]} `
              : ""}
            {COVERAGE_LABEL[match.coverage_type]}
          </div>
        </div>
      </td>

      {/* Model probabilities */}
      <td className="py-3 px-3 w-44">
        <div className="flex flex-col gap-[3px]">
          <ProbBar label="H" value={match.prob_h} highlighted={match.recommendation === "H"} delay={barDelay} />
          <ProbBar label="U" value={match.prob_u} highlighted={match.recommendation === "U"} delay={barDelay + 80} />
          <ProbBar label="B" value={match.prob_b} highlighted={match.recommendation === "B"} delay={barDelay + 160} />
        </div>
      </td>

      {/* Crowd */}
      <td className="py-3 px-3 w-20">
        {crowd ? (
          <div className="flex flex-col gap-[3px]">
            {crowd.map(({ label, v }) => (
              <div key={label} className="flex items-center gap-1.5">
                <span className="text-[10px] text-slate-700 w-3 text-right shrink-0 font-medium">
                  {label}
                </span>
                <span
                  className={cn(
                    "text-[10px] tabular-nums font-medium",
                    label === match.recommendation ? "text-slate-400" : "text-slate-700"
                  )}
                >
                  {Math.round(v * 100)}%
                </span>
              </div>
            ))}
          </div>
        ) : (
          <span className="text-[10px] text-slate-700">—</span>
        )}
      </td>

      {/* Edge */}
      <td className="py-3 px-3 text-right w-16">
        <EdgeBadge match={match} />
      </td>

      {/* VI */}
      <td className="py-3 px-3 text-center w-14">
        <ViBadge vi={match.vi} />
      </td>

      {/* CDS */}
      <td className="py-3 pr-4 pl-2 text-center w-16">
        <CdsBadge cds={match.crowd_disagreement_score} />
      </td>
    </tr>
  );
}

// ── Match table ───────────────────────────────────────────────────────────────

interface MatchTableProps {
  matches: MatchResult[];
  isLoading?: boolean;
}

const TH =
  "text-[9px] font-semibold text-slate-600 uppercase tracking-widest py-3 px-3 font-normal whitespace-nowrap";

export function MatchTable({ matches, isLoading }: MatchTableProps) {
  return (
    <div className="glass rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/[0.07]">
              <th className={cn(TH, "pl-4 pr-2 text-left w-8")}>#</th>
              <th className={cn(TH, "text-left")}>Kamp</th>
              <th className={cn(TH, "text-center w-24")}>Pick</th>
              <th className={cn(TH, "text-left w-44")}>Modell H/U/B</th>
              <th className={cn(TH, "text-left w-20")}>Folket</th>
              <th className={cn(TH, "text-right w-16")}>Edge</th>
              <th className={cn(TH, "text-center w-14")}>VI</th>
              <th className={cn(TH, "text-center w-16 pr-4")}>CDS</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 12 }, (_, i) => <SkeletonRow key={i} i={i} />)
              : matches.map((m, i) => (
                  <MatchRow key={m.match_number} match={m} index={i} />
                ))}
          </tbody>
        </table>
      </div>

      {!isLoading && matches.length === 0 && (
        <div className="py-16 text-center text-slate-600 text-sm">
          Ingen kamper tilgjengelig
        </div>
      )}
    </div>
  );
}
