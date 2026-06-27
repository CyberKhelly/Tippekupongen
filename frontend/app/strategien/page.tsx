"use client";

import { useState, useMemo, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { optimize, getEnrichment, getCouponDetail } from "@/lib/api";
import type { MatchEnrichment, MatchResult } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { Logo } from "@/components/brand/Logo";
import { SystemMatchRow } from "@/components/SystemMatchRow";
import type { Sign } from "@/components/SystemMatchRow";
import { cn } from "@/lib/utils";
import { useCouponQuery } from "@/hooks/useCouponQuery";
import { SYSTEM_LIBRARY } from "@/lib/systemLibrary";
import type { SystemPreset } from "@/lib/systemLibrary";

type SignState = Record<number, Set<Sign>>;
type CoverageType = "key" | "reserve" | "single";
type CoverageState = Record<number, CoverageType>;

type MatchExplain = {
  matchNumber: number;
  coverageScore: number;
  coverageRank: number;
  population: "eligible" | "anchor-only";
  coverageType: CoverageType;
  anchor: Sign;
  reserve: Sign | null;
  threshold: number;
  reason: string;
};

// ── System proposal builder (anchor-first architecture) ───────────────────────
//
// Three distinct concepts:
//
//   ANCHOR   — what the model genuinely believes will happen.
//              Driven by model probability. High-probability signs only.
//              Morocco H=90% → anchor H, always. Never let VI override this.
//
//   RESERVE  — given the anchor fails, which alternative rows should survive?
//              Model plausibility is the floor (7% sign can't beat 25% on VI alone).
//              After plausibility is satisfied, value/VI/edge break ties.
//
//   COVERAGE — how many outcomes to include per match (single / half / full).
//              Driven by uncertainty + CDS + positive-edge spread across outcomes.
//              Does NOT affect which sign is the anchor — only how many outcomes to cover.
//
// Row distribution per coverage type:
//   full  (H+U+B) — most rows contain any outcome; used for genuinely uncertain matches
//   half  (anchor+reserve) — most rows go to anchor, some survive via reserve
//   single (anchor) — all rows carry a single belief; used for confident matches

// Cheap systems are conservative; expensive ones allow more CDS-driven coverage decisions.
function systemAggressiveness(rows: number): number {
  if (rows < 100) return 0.3;
  if (rows < 300) return 0.6;
  return 1.0;
}

// Anchor: the outcome the model believes will happen.
// Strictly highest model probability — VI/edge/CDS do NOT influence this.
function computeAnchor(m: MatchResult): Sign {
  if (m.prob_h >= m.prob_u && m.prob_h >= m.prob_b) return "H";
  if (m.prob_u >= m.prob_b) return "U";
  return "B";
}

// Reserve: given the anchor, which fallback sign gives the best row-survival value?
// Model probability provides the plausibility floor (50% weight) so marginal outcomes
// (e.g. Morocco U=7%) cannot overtake plausible ones (B=25%) purely on VI.
// VI/edge/CDS are secondary factors that break ties and reward value reserves.
function computeReserve(m: MatchResult, anchor: Sign): Sign {
  const candidates = (["H", "U", "B"] as Sign[]).filter((s) => s !== anchor);
  const scored = candidates.map((s) => {
    const modelP   = s === "H" ? m.prob_h    : s === "U" ? m.prob_u    : m.prob_b;
    const bmP      = s === "H" ? m.bm_prob_h : s === "U" ? m.bm_prob_u : m.bm_prob_b;
    const pubP     = s === "H" ? m.pub_prob_h : s === "U" ? m.pub_prob_u : m.pub_prob_b;
    const edge     = s === "H" ? m.value_h   : s === "U" ? m.value_u   : m.value_b;
    const vi       = pubP != null && pubP > 0.02 ? bmP / pubP : null;
    const viNorm   = vi   != null ? Math.min(1, Math.max(0, (vi - 0.6) / 0.8)) : 0.5;
    const edgeNorm = Math.min(1, Math.max(0, ((edge ?? 0) + 15) / 30));
    const cdsNorm  = Math.min(1, Math.max(0, (m.crowd_disagreement_score ?? 0) / 1.5));
    return {
      sign: s,
      score: modelP * 0.50 + viNorm * 0.30 + edgeNorm * 0.15 + cdsNorm * 0.05,
    };
  });
  scored.sort((a, b) => b.score - a.score);
  return scored[0].sign;
}

// Coverage score: how uncertain / valuable is it to add more outcomes to this match?
// High uncertainty + high CDS + multiple positive-edge outcomes → more rows needed.
function matchCoverageScore(m: MatchResult, aggressiveness: number): number {
  const maxP = Math.max(m.prob_h, m.prob_u, m.prob_b);
  const cds  = m.crowd_disagreement_score ?? 0;
  const positiveEdges = ([m.value_h, m.value_u, m.value_b] as (number | null)[])
    .filter((v) => v != null && v > 0).length;
  return (
    (1 - maxP) * (0.65 + aggressiveness * 0.10) +
    Math.min(cds / 1.5, 1) * 0.20 * aggressiveness +
    positiveEdges * 0.05
  );
}

// Absolute threshold: matches below this are always anchor-only, never covered.
// Coverage is a scarce resource — very strong favourites (e.g. H=90%) must not
// absorb half/full cover slots just because they rank highest in a low-uncertainty pool.
// Morocco H=90%: score ≈ 0.075 → below threshold at all aggressiveness levels.
// Japan H=70%:   score ≈ 0.21+ → above threshold for balanced/aggressive systems.
function minCoverageThreshold(aggressiveness: number): number {
  return 0.22 - aggressiveness * 0.08; // 0.22 conservative → 0.14 aggressive
}

const CANONICAL: Sign[] = ["H", "U", "B"];

// Cartesian product of sign sets → exact row matrix for Category A systems.
// Each entry in the result is one complete row of 12 signs.
function generateRows(matches: MatchResult[], signState: SignState): Sign[][] {
  const signSets = matches.map((m) => Array.from(signState[m.match_number] ?? new Set<Sign>()));
  return signSets.reduce<Sign[][]>(
    (acc, set) => acc.flatMap((row) => set.map((sign) => [...row, sign])),
    [[]],
  );
}

// Coverage plan — two paths based on system category:
//
//   Category A — Rank-forced (no threshold):
//     All n_full + n_half coverage slots are always filled in score order.
//     This guarantees exactly 3^n_full × 2^n_half rows, verified against system.rows.
//     Coverage score still controls WHICH matches get coverage, just not WHETHER.
//
//   Category B — Threshold-gated (legacy path, disabled in UI):
//     Matches below the threshold stay anchor-only regardless of remaining slots.
//     This path should not be reached since Category B systems are disabled.
function buildSystemProposal(
  system: SystemPreset,
  matches: MatchResult[],
): { signState: SignState; coverageState: CoverageState; explains: MatchExplain[]; rowMatrix: Sign[][] | null } {
  const agg = systemAggressiveness(system.rows);

  const withScores = matches.map((m) => ({ match: m, score: matchCoverageScore(m, agg) }));
  withScores.sort((a, b) => b.score - a.score);

  const globalRankMap = new Map<number, number>();
  withScores.forEach(({ match }, i) => globalRankMap.set(match.match_number, i + 1));

  const signState: SignState = {};
  const coverageState: CoverageState = {};
  const explains: MatchExplain[] = [];

  if (system.category === "A") {
    // ── Category A: rank-forced, exact row count ────────────────────────────────
    withScores.forEach(({ match, score }, i) => {
      const rank   = globalRankMap.get(match.match_number)!;
      const anchor = computeAnchor(match);
      const maxP   = Math.max(match.prob_h, match.prob_u, match.prob_b);

      if (i < system.n_full) {
        signState[match.match_number] = new Set(["H", "U", "B"] as Sign[]);
        coverageState[match.match_number] = "key";
        explains.push({
          matchNumber: match.match_number,
          coverageScore: score,
          coverageRank: rank,
          population: "eligible",
          coverageType: "key",
          anchor,
          reserve: null,
          threshold: 0,
          reason: `Full cover. Rank ${rank}/${matches.length} by coverage score. Dominant P=${Math.round(maxP * 100)}%. Covers H+U+B.`,
        });
      } else if (i < system.n_full + system.n_half) {
        const reserve = computeReserve(match, anchor);
        const pair    = ([anchor, reserve] as Sign[]).sort(
          (a, b) => CANONICAL.indexOf(a) - CANONICAL.indexOf(b),
        );
        signState[match.match_number] = new Set(pair);
        coverageState[match.match_number] = "reserve";
        const anchorP = anchor === "H" ? match.prob_h : anchor === "U" ? match.prob_u : match.prob_b;
        explains.push({
          matchNumber: match.match_number,
          coverageScore: score,
          coverageRank: rank,
          population: "eligible",
          coverageType: "reserve",
          anchor,
          reserve,
          threshold: 0,
          reason: `Half cover. Rank ${rank}/${matches.length}. Anchor: ${anchor} (${Math.round(anchorP * 100)}%). Reserve: ${reserve} by model plausibility + value.`,
        });
      } else {
        signState[match.match_number] = new Set([anchor]);
        coverageState[match.match_number] = "single";
        explains.push({
          matchNumber: match.match_number,
          coverageScore: score,
          coverageRank: rank,
          population: "anchor-only",
          coverageType: "single",
          anchor,
          reserve: null,
          threshold: 0,
          reason: `Single (rank ${rank}/${matches.length}). All ${system.n_full} full + ${system.n_half} half slots filled by higher-priority matches. Dominant P=${Math.round(maxP * 100)}%.`,
        });
      }
    });

    const rowMatrix = generateRows(matches, signState);
    if (rowMatrix.length !== system.rows) {
      console.error(
        `[Row count mismatch] ${system.name}: expected ${system.rows}, got ${rowMatrix.length}. ` +
        `Check n_full=${system.n_full} n_half=${system.n_half} (3^${system.n_full} × 2^${system.n_half} = ${Math.pow(3, system.n_full) * Math.pow(2, system.n_half)})`,
      );
    }
    return { signState, coverageState, explains, rowMatrix };
  }

  // ── Category B: threshold-gated (disabled in UI, kept for completeness) ────────
  const threshold = minCoverageThreshold(agg);
  const eligible   = withScores.filter((x) => x.score >= threshold);
  const anchorOnly = withScores.filter((x) => x.score <  threshold);

  eligible.forEach(({ match, score }, i) => {
    const rank   = globalRankMap.get(match.match_number)!;
    const anchor = computeAnchor(match);
    const maxP   = Math.max(match.prob_h, match.prob_u, match.prob_b);

    if (i < system.n_full) {
      signState[match.match_number] = new Set(["H", "U", "B"] as Sign[]);
      coverageState[match.match_number] = "key";
      explains.push({
        matchNumber: match.match_number, coverageScore: score, coverageRank: rank,
        population: "eligible", coverageType: "key", anchor, reserve: null, threshold,
        reason: `Full cover. Score ${score.toFixed(3)} ≥ ${threshold.toFixed(3)}. Dominant P=${Math.round(maxP * 100)}%.`,
      });
    } else if (i < system.n_full + system.n_half) {
      const reserve = computeReserve(match, anchor);
      const pair    = ([anchor, reserve] as Sign[]).sort(
        (a, b) => CANONICAL.indexOf(a) - CANONICAL.indexOf(b),
      );
      signState[match.match_number] = new Set(pair);
      coverageState[match.match_number] = "reserve";
      const anchorP = anchor === "H" ? match.prob_h : anchor === "U" ? match.prob_u : match.prob_b;
      explains.push({
        matchNumber: match.match_number, coverageScore: score, coverageRank: rank,
        population: "eligible", coverageType: "reserve", anchor, reserve, threshold,
        reason: `Half cover. Anchor: ${anchor} (${Math.round(anchorP * 100)}%). Reserve: ${reserve}.`,
      });
    } else {
      signState[match.match_number] = new Set([anchor]);
      coverageState[match.match_number] = "single";
      explains.push({
        matchNumber: match.match_number, coverageScore: score, coverageRank: rank,
        population: "eligible", coverageType: "single", anchor, reserve: null, threshold,
        reason: `Eligible but coverage slots exhausted. Anchor: ${anchor}.`,
      });
    }
  });

  anchorOnly.forEach(({ match, score }) => {
    const rank   = globalRankMap.get(match.match_number)!;
    const anchor = computeAnchor(match);
    const maxP   = Math.max(match.prob_h, match.prob_u, match.prob_b);
    signState[match.match_number] = new Set([anchor]);
    coverageState[match.match_number] = "single";
    explains.push({
      matchNumber: match.match_number, coverageScore: score, coverageRank: rank,
      population: "anchor-only", coverageType: "single", anchor, reserve: null, threshold,
      reason: `Anchor-only. Score ${score.toFixed(3)} < ${threshold.toFixed(3)}. Dominant P=${Math.round(maxP * 100)}%.`,
    });
  });

  return { signState, coverageState, explains, rowMatrix: null };
}

// ── Page header ────────────────────────────────────────────────────────────────

function PageHeader({ isConnected }: { isConnected: boolean }) {
  return (
    <header className="sticky top-0 z-20 bg-[#0D0D0D] border-b border-[rgba(255,255,255,0.07)]">
      <div
        className="max-w-screen-xl mx-auto px-4 sm:px-6 flex items-center justify-between"
        style={{ height: 52 }}
      >
        <motion.div
          className="flex items-center gap-3"
          initial={{ opacity: 0, x: -8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <Logo size="sm" theme="dark" />
          <span className="hidden sm:inline-flex items-center h-5 px-2 rounded border border-[rgba(255,255,255,0.1)] bg-[#141414] text-[10px] font-semibold text-[#4A4744] tracking-wide">
            Systemspill
          </span>
        </motion.div>

        <motion.div
          className="flex items-center gap-2"
          initial={{ opacity: 0, x: 8 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.4, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
        >
          <span className="relative flex h-2 w-2">
            <span className={cn(
              "absolute inline-flex h-full w-full rounded-full opacity-60",
              isConnected ? "bg-[#22C55E] animate-ping" : "bg-[#F05252]",
            )} />
            <span className={cn(
              "relative inline-flex rounded-full h-2 w-2",
              isConnected ? "bg-[#22C55E]" : "bg-[#F05252]",
            )} />
          </span>
          <span className="text-[11px] text-[#4A4744] font-medium hidden sm:block">
            {isConnected ? "tilkoblet" : "frakoblet"}
          </span>
        </motion.div>
      </div>
    </header>
  );
}

// ── System selector + metrics strip ───────────────────────────────────────────

function SystemStrip({
  activeSystemId, onSelect, rows, cost, disabled, debugMode, onToggleDebug,
}: {
  activeSystemId: string | null;
  onSelect: (id: string) => void;
  rows: number;
  cost: number;
  disabled: boolean;
  debugMode: boolean;
  onToggleDebug: () => void;
}) {
  const [open, setOpen] = useState(false);
  const activeSystem = SYSTEM_LIBRARY.find((s) => s.id === activeSystemId) ?? null;

  return (
    <div className="sticky top-[52px] z-10 bg-[#0D0D0D] border-b border-[rgba(255,255,255,0.07)]">
      <div className="max-w-screen-xl mx-auto px-4 sm:px-6 py-3">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center">

          {/* System dropdown */}
          <div className="relative flex items-center gap-1.5">
            <span className="text-[9px] font-semibold text-[#4A4744] uppercase tracking-widest shrink-0 mr-0.5 hidden sm:block">
              System
            </span>

            <button
              onClick={() => !disabled && setOpen((o) => !o)}
              disabled={disabled}
              className={cn(
                "h-7 px-2.5 rounded-lg text-[11px] font-semibold border transition-all duration-150",
                "focus:outline-none focus-visible:ring-2 focus-visible:ring-[#F5C030]/30",
                "disabled:pointer-events-none disabled:opacity-40",
                "flex items-center gap-1.5",
                activeSystem
                  ? "bg-[#E8E4DD] text-[#0D0D0D] border-[#E8E4DD]"
                  : "bg-[#1C1C1C] text-[#7A7673] border-[rgba(255,255,255,0.07)] hover:border-[rgba(255,255,255,0.15)] hover:text-[#E8E4DD]",
              )}
            >
              <span>
                {activeSystem
                  ? activeSystem.name
                  : activeSystemId === "custom"
                  ? "Egendefinert"
                  : "Velg system"}
              </span>
              {activeSystem && (
                <span className="text-[9px] tabular-nums text-[#4A4744]">
                  {activeSystem.rows.toLocaleString("nb-NO")}
                </span>
              )}
              <span className={cn("text-[8px]", activeSystem ? "text-[#4A4744]" : "text-[#4A4744]")}>
                {open ? "▲" : "▼"}
              </span>
            </button>

            {/* Overlay to close on outside click */}
            {open && (
              <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
            )}

            {/* Dropdown panel */}
            {open && (
              <div className="absolute top-full left-0 mt-1.5 z-50 min-w-[360px] bg-[#141414] border border-[rgba(255,255,255,0.1)] rounded-xl shadow-[0_4px_24px_rgba(0,0,0,0.5)] overflow-hidden">
                {/* Column headers */}
                <div className="flex items-center px-3 pt-2.5 pb-1.5 border-b border-[rgba(255,255,255,0.06)]">
                  <span className="flex-1 min-w-[96px] text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">System</span>
                  <span className="w-[62px] text-right text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Utganger</span>
                  <span className="w-[62px] text-right text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Reserver</span>
                  <span className="w-14 text-right text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Rekker</span>
                  <span className="w-[72px] text-right text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest pr-0.5">Kostnad</span>
                </div>

                {/* System rows */}
                <div className="overflow-y-auto max-h-[min(420px,calc(100vh-160px))]">
                {SYSTEM_LIBRARY.map((system) => {
                  const isActive  = system.id === activeSystemId;
                  const isCatA    = system.category === "A";
                  const isDisabled = !isCatA;
                  return (
                    <div
                      key={system.id}
                      role={isDisabled ? undefined : "button"}
                      tabIndex={isDisabled ? -1 : 0}
                      onClick={() => { if (!isDisabled) { onSelect(system.id); setOpen(false); } }}
                      onKeyDown={(e) => {
                        if (!isDisabled && (e.key === " " || e.key === "Enter")) {
                          e.preventDefault(); onSelect(system.id); setOpen(false);
                        }
                      }}
                      className={cn(
                        "w-full flex items-center px-3 py-2 text-left",
                        isDisabled
                          ? "cursor-not-allowed opacity-40"
                          : cn("cursor-pointer transition-colors duration-100", isActive ? "bg-[#1C1C1C]" : "hover:bg-[rgba(255,255,255,0.04)]"),
                      )}
                    >
                      <div className="flex-1 flex items-center gap-1.5 min-w-[96px] shrink-0">
                        <span className={cn(
                          "text-[11px] font-semibold whitespace-nowrap",
                          isDisabled ? "text-[#3A3735]" : isActive ? "text-[#E8E4DD]" : "text-[#7A7673]",
                        )}>
                          {system.name}
                        </span>
                        {isActive && !isDisabled && (
                          <span className="text-[9px] text-[#F5C030] leading-none">✓</span>
                        )}
                        {isDisabled && (
                          <span
                            className="text-[8px] text-[#3A3735] italic"
                            title="Krever offisiell reduksjonsmatrise fra NT"
                          >
                            (B)
                          </span>
                        )}
                      </div>
                      <span className={cn(
                        "w-[62px] text-right text-[11px] tabular-nums",
                        isDisabled ? "text-[#2A2724]" : "text-[#4A4744]",
                      )}>{system.utganger}</span>
                      <span className={cn(
                        "w-[62px] text-right text-[11px] tabular-nums",
                        isDisabled ? "text-[#2A2724]" : "text-[#4A4744]",
                      )}>{system.reserver}</span>
                      <span className={cn(
                        "w-14 text-right text-[11px] tabular-nums font-semibold",
                        isDisabled ? "text-[#2A2724]" : isActive ? "text-[#E8E4DD]" : "text-[#4A4744]",
                      )}>
                        {system.rows.toLocaleString("nb-NO")}
                      </span>
                      <span className={cn(
                        "w-[72px] text-right text-[11px] tabular-nums pr-0.5",
                        isDisabled ? "text-[#2A2724]" : "text-[#4A4744]",
                      )}>
                        {system.cost.toLocaleString("nb-NO")} kr
                      </span>
                    </div>
                  );
                })}
                </div>
              </div>
            )}
          </div>

          {/* Live metrics */}
          <div className="flex items-center gap-4 sm:ml-auto text-[12px]">
            <div className="flex items-baseline gap-1.5">
              <span className="text-[9px] text-[#4A4744] uppercase tracking-widest font-semibold">Rader</span>
              <span className="font-bold tabular-nums text-[#E8E4DD]">
                {rows > 0 ? rows.toLocaleString("nb-NO") : "—"}
              </span>
            </div>
            <span className="text-[rgba(255,255,255,0.1)]">·</span>
            <div className="flex items-baseline gap-1.5">
              <span className="text-[9px] text-[#4A4744] uppercase tracking-widest font-semibold">Kostnad</span>
              <span className="font-bold tabular-nums text-[#E8E4DD]">
                {cost > 0 ? `${cost.toLocaleString("nb-NO")} kr` : "—"}
              </span>
            </div>
            <span className="text-[rgba(255,255,255,0.1)]">·</span>
            <button
              onClick={onToggleDebug}
              title="Vis debug-info per tegn"
              className={cn(
                "text-[9px] font-semibold uppercase tracking-widest transition-colors",
                debugMode ? "text-[#F5C030]" : "text-[#4A4744] hover:text-[#7A7673]",
              )}
            >
              Debug
            </button>
          </div>

        </div>
      </div>
    </div>
  );
}

// ── Table header row ───────────────────────────────────────────────────────────

const TH = "text-[9px] font-semibold text-[#4A4744] uppercase tracking-[1.2px] whitespace-nowrap";

function TableHeader() {
  return (
    <div className="flex items-start gap-3 px-4 pt-2.5 pb-2 border-b border-[rgba(255,255,255,0.07)] bg-[#0D0D0D]">
      <span className="w-5 shrink-0" />
      <span className={cn(TH, "flex-1 pt-[1px]")}>Kamp</span>
      <div className="flex gap-2 shrink-0">
        {(["H", "U", "B"] as Sign[]).map((s) => (
          <div key={s} className="flex flex-col items-center" style={{ width: 52 }}>
            <span className={cn(TH, "text-center")}>{s}</span>
            <div className="flex flex-col items-center mt-1" style={{ gap: 1 }}>
              {(["Odds", "Folket", "VI"] as const).map((lbl) => (
                <span
                  key={lbl}
                  style={{
                    fontSize: 7,
                    fontWeight: 500,
                    color: "#3A3735",
                    lineHeight: 1.5,
                    letterSpacing: "0.04em",
                  }}
                >
                  {lbl}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Skeleton row ───────────────────────────────────────────────────────────────

function SkeletonRow({ delay }: { delay: number }) {
  return (
    <div
      className="flex items-center gap-3 px-4 border-b border-[rgba(255,255,255,0.06)]"
      style={{ paddingTop: 10, paddingBottom: 10, animationDelay: `${delay}ms` }}
    >
      <div className="w-5 h-3 bg-[#1C1C1C] rounded animate-pulse shrink-0" />
      <div className="flex-1 space-y-1.5">
        <div className="h-3 w-28 bg-[#1C1C1C] rounded animate-pulse" />
        <div className="h-2.5 w-20 bg-[#1C1C1C] rounded animate-pulse" />
      </div>
      <div className="flex gap-2 shrink-0">
        {[0, 1, 2].map((j) => (
          <div key={j} className="flex flex-col items-center gap-1.5" style={{ width: 52 }}>
            <div className="w-7 h-7 bg-[#1C1C1C] rounded animate-pulse" />
            <div className="w-8 h-2 bg-[#1C1C1C] rounded animate-pulse" />
            <div className="w-6 h-2 bg-[#1C1C1C] rounded animate-pulse" />
            <div className="w-7 h-2 bg-[#1C1C1C] rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function StrategienPage() {
  const { coupons, selectedCouponId, setSelectedCouponId, isApiOffline, isCouponsLoading } =
    useCouponQuery();

  const [signState, setSignState] = useState<SignState>({});
  const [coverageState, setCoverageState] = useState<CoverageState>({});
  const [activeSystemId, setActiveSystemId] = useState<string | null>(null);
  const [debugMode, setDebugMode] = useState(false);
  const [explainData, setExplainData] = useState<MatchExplain[]>([]);
  const [rowMatrix, setRowMatrix] = useState<Sign[][] | null>(null);

  // ── Queries ──────────────────────────────────────────────────────────────────

  const optimizeQuery = useQuery({
    queryKey: ["optimize", selectedCouponId, "balanced", 192],
    queryFn: () =>
      optimize({ coupon_id: selectedCouponId!, strategy: "balanced", budget: 192 }),
    enabled: !!selectedCouponId,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const enrichmentQuery = useQuery({
    queryKey: ["enrichment", selectedCouponId],
    queryFn: () => getEnrichment(selectedCouponId!),
    enabled: !!selectedCouponId,
    staleTime: 10 * 60_000,
    retry: 1,
  });

  const couponDetailQuery = useQuery({
    queryKey: ["coupon-detail", selectedCouponId],
    queryFn: () => getCouponDetail(selectedCouponId!),
    enabled: !!selectedCouponId,
    staleTime: 10 * 60_000,
    retry: 1,
  });

  const matches = optimizeQuery.data?.matches ?? [];

  const enrichmentMap = useMemo(
    () =>
      new Map<number, MatchEnrichment>(
        (enrichmentQuery.data ?? []).map((e) => [e.match_number, e]),
      ),
    [enrichmentQuery.data],
  );

  const kickoffMap = useMemo(
    () =>
      new Map<number, string | null>(
        (couponDetailQuery.data?.matches ?? []).map((m) => [m.match_number, m.kickoff_utc]),
      ),
    [couponDetailQuery.data],
  );

  // Reset when coupon changes
  useEffect(() => {
    setSignState({});
    setCoverageState({});
    setExplainData([]);
    setRowMatrix(null);
    setActiveSystemId(null);
  }, [selectedCouponId]);

  // ── Interactions ─────────────────────────────────────────────────────────────

  const handleToggle = (matchNumber: number, sign: Sign) => {
    setActiveSystemId("custom");
    setCoverageState({});
    setExplainData([]);
    setRowMatrix(null);
    setSignState((prev) => {
      const current = new Set(prev[matchNumber] ?? []);
      if (current.has(sign)) current.delete(sign);
      else current.add(sign);
      return { ...prev, [matchNumber]: current };
    });
  };

  const handleSystem = (id: string) => {
    if (!matches.length) return;
    const system = SYSTEM_LIBRARY.find((s) => s.id === id);
    if (!system) return;
    const proposal = buildSystemProposal(system, matches);
    setActiveSystemId(id);
    setSignState(proposal.signState);
    setCoverageState(proposal.coverageState);
    setExplainData(proposal.explains);
    setRowMatrix(proposal.rowMatrix);

    if (debugMode) {
      const n = matches.length;
      console.group(`[Systemspill Explain] ${system.name} · threshold=${proposal.explains[0]?.threshold?.toFixed(3)}`);
      [...proposal.explains]
        .sort((a, b) => a.coverageRank - b.coverageRank)
        .forEach((ex) => {
          const m = matches.find((mm) => mm.match_number === ex.matchNumber);
          if (!m) return;
          const signs = Array.from(proposal.signState[ex.matchNumber] ?? new Set<Sign>()).join("+");
          const vi = (s: Sign) => {
            const pub = s === "H" ? m.pub_prob_h : s === "U" ? m.pub_prob_u : m.pub_prob_b;
            const bm  = s === "H" ? m.bm_prob_h  : s === "U" ? m.bm_prob_u  : m.bm_prob_b;
            return pub != null && pub > 0.02 ? (bm / pub).toFixed(2) : "—";
          };
          console.log(
            `[${String(ex.coverageRank).padStart(2)}/${n}] ${m.home_team} – ${m.away_team}\n` +
            `  signs=${signs} | pop=${ex.population} | type=${ex.coverageType}\n` +
            `  score=${ex.coverageScore.toFixed(3)} threshold=${ex.threshold.toFixed(3)}\n` +
            `  anchor=${ex.anchor} reserve=${ex.reserve ?? "—"}\n` +
            `  mod  H=${(m.prob_h*100).toFixed(1)}% U=${(m.prob_u*100).toFixed(1)}% B=${(m.prob_b*100).toFixed(1)}%\n` +
            `  bm   H=${(m.bm_prob_h*100).toFixed(1)}% U=${(m.bm_prob_u*100).toFixed(1)}% B=${(m.bm_prob_b*100).toFixed(1)}%\n` +
            `  pub  H=${m.pub_prob_h != null ? (m.pub_prob_h*100).toFixed(1) : "?"}%` +
            ` U=${m.pub_prob_u != null ? (m.pub_prob_u*100).toFixed(1) : "?"}%` +
            ` B=${m.pub_prob_b != null ? (m.pub_prob_b*100).toFixed(1) : "?"}%\n` +
            `  VI   H=${vi("H")} U=${vi("U")} B=${vi("B")}\n` +
            `  edge H=${m.value_h != null ? `${m.value_h > 0 ? "+" : ""}${m.value_h.toFixed(1)}pp` : "?"}` +
            ` U=${m.value_u != null ? `${m.value_u > 0 ? "+" : ""}${m.value_u.toFixed(1)}pp` : "?"}` +
            ` B=${m.value_b != null ? `${m.value_b > 0 ? "+" : ""}${m.value_b.toFixed(1)}pp` : "?"}\n` +
            `  CDS=${(m.crowd_disagreement_score ?? 0).toFixed(3)}\n` +
            `  → ${ex.reason}`
          );
        });
      console.groupEnd();
    }
  };

  // ── Derived metrics ───────────────────────────────────────────────────────────

  const { naiveRows, inSystemCount } = useMemo(() => {
    const withSigns = matches.filter((m) => (signState[m.match_number]?.size ?? 0) > 0);
    const naive = withSigns.length
      ? withSigns.reduce((acc, m) => acc * signState[m.match_number]!.size, 1)
      : 0;
    // When a system is active: "I system" = key + reserve matches.
    // In manual/custom mode: "I system" = matches with ≥2 signs.
    const isSystemActive = !!activeSystemId && activeSystemId !== "custom";
    const multiCount = isSystemActive
      ? matches.filter(
          (m) =>
            coverageState[m.match_number] === "key" ||
            coverageState[m.match_number] === "reserve",
        ).length
      : matches.filter((m) => (signState[m.match_number]?.size ?? 0) >= 2).length;
    return { naiveRows: naive, inSystemCount: multiCount };
  }, [signState, matches, coverageState, activeSystemId]);

  // When a system is active, show the library's official row/cost values.
  // Otherwise fall back to the naive combinatorial count from sign state.
  const activeSystem = SYSTEM_LIBRARY.find((s) => s.id === activeSystemId) ?? null;
  const displayRows = activeSystem?.rows ?? naiveRows;
  const displayCost = activeSystem?.cost ?? naiveRows;

  const isLoading = optimizeQuery.isLoading || optimizeQuery.isFetching;
  const isConnected = !isApiOffline;

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <div className="relative min-h-screen bg-[#0D0D0D]">
      <PageHeader isConnected={isConnected} />

      <SystemStrip
        activeSystemId={activeSystemId}
        onSelect={handleSystem}
        rows={displayRows}
        cost={displayCost}
        disabled={isLoading || !matches.length}
        debugMode={debugMode}
        onToggleDebug={() => setDebugMode((d) => !d)}
      />

      <main className="max-w-screen-xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
        {/* Offline banner */}
        <AnimatePresence>
          {isApiOffline && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="mb-5 p-3.5 rounded-xl border border-[#F05252]/20 bg-[#F05252]/[0.06] text-sm text-[#F05252] flex items-start gap-3"
            >
              <span className="mt-0.5 shrink-0">⚠</span>
              <div>
                Backend kjører ikke.{" "}
                <code className="text-[11px] font-mono bg-[#F05252]/[0.1] px-1 rounded">
                  .\start-dev.ps1
                </code>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Coupon selector */}
        <motion.div
          className="mb-6"
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
        >
          <CouponSelector
            coupons={coupons}
            selected={selectedCouponId}
            onSelect={setSelectedCouponId}
            isLoading={isCouponsLoading}
          />
        </motion.div>

        {/* Hjelpetekst */}
        <AnimatePresence>
          {!isLoading && matches.length > 0 && !activeSystemId && (
            <motion.p
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mb-4 text-[12px] text-[#4A4744]"
            >
              Velg et system ovenfor, eller klikk H / U / B for å bygge din egen kupong.
            </motion.p>
          )}
        </AnimatePresence>
        <AnimatePresence>
          {!isLoading && matches.length > 0 && !!activeSystemId && activeSystemId !== "custom" && (
            <motion.p
              key="system"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="mb-4 text-[12px] text-[#4A4744]"
            >
              {activeSystem?.category === "A"
                ? `${activeSystem.name} — ${activeSystem.rows.toLocaleString("nb-NO")} rekker, fullt implementert. Klikk Debug for å se rekker.`
                : "Dette er en modellbasert systemplan. Full reduksjonsmatrise/garanti kommer senere."}
            </motion.p>
          )}
        </AnimatePresence>

        {/* Explain table — visible when Debug is ON and a system is active */}
        <AnimatePresence>
          {debugMode && !!activeSystemId && activeSystemId !== "custom" && explainData.length > 0 && (
            <motion.div
              key="explain"
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.25 }}
              className="mb-4 rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#141414] overflow-hidden"
            >
              {/* Header */}
              <div className="flex items-center gap-2 px-4 py-2 bg-[#0D0D0D] border-b border-[rgba(255,255,255,0.07)]">
                <span className="text-[9px] font-semibold text-[#F5C030] uppercase tracking-widest">
                  Explain
                </span>
                <span className="text-[9px] text-[#4A4744] font-medium">
                  · {activeSystem?.name}
                </span>
                {activeSystem?.category === "A" ? (
                  <span className="ml-auto text-[9px] text-[#3A3735]">
                    Kategori A · rangbasert · hover for begrunnelse · konsoll for fullt sett
                  </span>
                ) : (
                  <span className="ml-auto text-[9px] text-[#3A3735] tabular-nums">
                    terskel {explainData[0]?.threshold.toFixed(3)} · hover for begrunnelse · konsoll for fullt sett
                  </span>
                )}
              </div>

              {/* Column headers */}
              <div
                className="grid px-4 py-1.5 border-b border-[rgba(255,255,255,0.06)] bg-[#0D0D0D]"
                style={{ gridTemplateColumns: "20px 1fr 56px 44px 88px 80px 56px" }}
              >
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">#</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Kamp</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest text-right">Score</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest text-right">Rank</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Pop.</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Type</span>
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-widest">Tegn</span>
              </div>

              {/* Data rows sorted by coverage rank */}
              {[...explainData]
                .sort((a, b) => a.coverageRank - b.coverageRank)
                .map((ex) => {
                  const m = matches.find((mm) => mm.match_number === ex.matchNumber);
                  if (!m) return null;
                  const isAnchorOnly = ex.population === "anchor-only";
                  const signs = Array.from(signState[ex.matchNumber] ?? new Set<Sign>()).join("+");
                  return (
                    <div
                      key={ex.matchNumber}
                      className="grid items-center px-4 border-b border-[rgba(255,255,255,0.06)] last:border-0 cursor-default"
                      style={{
                        gridTemplateColumns: "20px 1fr 56px 44px 88px 80px 56px",
                        paddingTop: 5,
                        paddingBottom: 5,
                        opacity: isAnchorOnly ? 0.55 : 1,
                      }}
                      title={ex.reason}
                    >
                      <span className="text-[10px] tabular-nums text-[#3A3735]">{ex.matchNumber}</span>
                      <span className="text-[11px] text-[#E8E4DD] truncate pr-2">
                        {m.home_team} – {m.away_team}
                      </span>
                      <span className="text-[10px] tabular-nums text-[#4A4744] text-right">{ex.coverageScore.toFixed(3)}</span>
                      <span className="text-[10px] tabular-nums text-[#4A4744] text-right">{ex.coverageRank}/{matches.length}</span>
                      <span className={cn(
                        "text-[9px] font-semibold",
                        isAnchorOnly ? "text-[#3A3735]" : "text-[#22C55E]",
                      )}>
                        {isAnchorOnly ? "Anchor-only" : "Eligible"}
                      </span>
                      <span className={cn(
                        "text-[9px] font-medium",
                        ex.coverageType === "key"     ? "text-[#22C55E]" :
                        ex.coverageType === "reserve" ? "text-[#F5C030]" :
                        "text-[#4A4744]",
                      )}>
                        {ex.coverageType === "key"     ? "Helgardering" :
                         ex.coverageType === "reserve" ? "Halvgardering" :
                         "Singel"}
                      </span>
                      <span className="text-[11px] font-semibold tabular-nums text-[#E8E4DD]">
                        {signs || "—"}
                      </span>
                    </div>
                  );
                })}

              {/* Row count verification + matrix preview — Category A only */}
              {rowMatrix !== null && activeSystem?.category === "A" && (() => {
                const ok = rowMatrix.length === activeSystem.rows;
                const previewN = Math.min(5, rowMatrix.length);
                return (
                  <div className="px-4 py-3 bg-[#0D0D0D] border-t border-[rgba(255,255,255,0.07)]">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-[9px] font-semibold text-[#4A4744] uppercase tracking-widest">
                        Genererte rader
                      </span>
                      <span className={cn(
                        "text-[11px] font-bold tabular-nums",
                        ok ? "text-[#22C55E]" : "text-[#F05252]",
                      )}>
                        {rowMatrix.length.toLocaleString("nb-NO")} / {activeSystem.rows.toLocaleString("nb-NO")} {ok ? "✓" : "✗"}
                      </span>
                      <span className="text-[9px] text-[#3A3735] ml-1">
                        (3<sup>{activeSystem.n_full}</sup> × 2<sup>{activeSystem.n_half}</sup>)
                      </span>
                    </div>
                    <div className="font-mono space-y-0.5">
                      {rowMatrix.slice(0, previewN).map((row, i) => (
                        <div key={i} className="flex items-center gap-0.5">
                          <span className="text-[8px] text-[#3A3735] w-4 text-right shrink-0 mr-1">{i + 1}.</span>
                          {row.map((sign, j) => (
                            <span
                              key={j}
                              className="text-[8px] w-4 text-center leading-none"
                              style={{
                                color: sign === "H" ? "#E8E4DD" : sign === "U" ? "#F5C030" : "#6098F2",
                                fontWeight: sign === "U" ? 700 : 600,
                              }}
                            >
                              {sign}
                            </span>
                          ))}
                        </div>
                      ))}
                      {rowMatrix.length > previewN && (
                        <div className="text-[8px] text-[#4A4744] pl-5 mt-1">
                          … og {(rowMatrix.length - previewN).toLocaleString("nb-NO")} rader til
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Match table */}
        <motion.div
          className="rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#141414] overflow-hidden"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        >
          <TableHeader />

          {isLoading ? (
            Array.from({ length: 12 }, (_, i) => (
              <SkeletonRow key={i} delay={i * 40} />
            ))
          ) : matches.length === 0 ? (
            <div className="py-16 text-center text-[13px] text-[#4A4744]">
              Ingen kampdata tilgjengelig
            </div>
          ) : (
            matches.map((match) => (
              <SystemMatchRow
                key={match.match_number}
                match={match}
                enrichment={enrichmentMap.get(match.match_number)}
                signs={signState[match.match_number] ?? new Set()}
                onToggle={(sign) => handleToggle(match.match_number, sign)}
                kickoffUtc={kickoffMap.get(match.match_number)}
                debugMode={debugMode}
                coverageType={coverageState[match.match_number]}
              />
            ))
          )}
        </motion.div>

        {/* Merknad om systemtype */}
        {inSystemCount > 0 && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-4 text-[11px] text-[#4A4744]"
          >
            {activeSystem?.category === "A"
              ? `${activeSystem.name}: ${activeSystem.rows.toLocaleString("nb-NO")} eksakte rekker generert som kartesisk produkt (3²ⁿ × 2ⁿ). Ingen reduksjonsmatrise nødvendig.`
              : "Radtelling er basert på antall valgte tegn per kamp. Klassiske U-systemer bruker matematiske reduksjonstabeller for å gi garantier — dette er en tilnærming."}
          </motion.p>
        )}
      </main>
    </div>
  );
}
