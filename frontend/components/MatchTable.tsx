"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { cn, recValue } from "@/lib/utils";
import type { MatchEnrichment, MatchResult, RecentMatch } from "@/lib/types";

// ── Outcome colors ────────────────────────────────────────────────────────────

const OUTCOME_COLORS: Record<string, string> = {
  H: "#3b82f6",
  U: "#52525b",
  B: "#10b981",
};

// ── Prob bar (main table column) ──────────────────────────────────────────────

function ProbBar({
  label, value, highlighted, delay,
}: { label: string; value: number; highlighted: boolean; delay: number }) {
  const pct = Math.round(value * 100);
  const color = OUTCOME_COLORS[label] ?? "#606060";
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span className={cn(
        "text-[10px] w-3 text-right shrink-0 tabular-nums font-medium",
        highlighted ? "text-zinc-400" : "text-zinc-700",
      )}>
        {label}
      </span>
      <div className="flex-1 h-[3px] rounded-full overflow-hidden min-w-[36px]" style={{ background: "#1a1a1a" }}>
        <div
          className="h-full rounded-full animate-bar-grow"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            opacity: highlighted ? 1 : 0.2,
            transformOrigin: "left",
            animationDelay: `${delay}ms`,
          }}
        />
      </div>
      <span className={cn(
        "text-[10px] tabular-nums w-6 text-right shrink-0 font-medium",
        highlighted ? "text-zinc-300" : "text-zinc-700",
      )}>
        {pct}%
      </span>
    </div>
  );
}

// ── Small summary badges ──────────────────────────────────────────────────────

function CdsBadge({ cds }: { cds: number | null }) {
  if (cds == null) return <span className="text-[10px] text-zinc-800">—</span>;
  const level = cds >= 20 ? "high" : cds >= 10 ? "mid" : "low";
  const cls = {
    high: "text-amber-300 bg-amber-400/[0.07] border border-amber-400/[0.16]",
    mid:  "text-zinc-400 bg-white/[0.03] border border-white/[0.05]",
    low:  "text-zinc-700",
  }[level];
  return (
    <span className={cn("text-[10px] tabular-nums font-semibold px-1.5 py-0.5 rounded", cls)}>
      {cds.toFixed(1)}
    </span>
  );
}

function ViBadge({ vi }: { vi: number | null }) {
  if (vi == null) return <span className="text-[10px] text-zinc-800">—</span>;
  const isHigh  = vi >= 1.2;
  const isAbove = vi > 1.0;
  const color = isHigh ? "text-emerald-400" : isAbove ? "text-zinc-300" : "text-red-400/70";
  return (
    <span className={cn("text-[10px] tabular-nums font-bold", color)}>
      {vi.toFixed(2)}
      <span className="text-[8px] ml-0.5 opacity-50">{isAbove ? "↑" : "↓"}</span>
    </span>
  );
}

function EdgeBadge({ match }: { match: MatchResult }) {
  if (!match.has_public_tips) return <span className="text-[10px] text-zinc-800">—</span>;
  const val = recValue(match.recommendation, match.value_h, match.value_u, match.value_b);
  if (val == null) return <span className="text-[10px] text-zinc-800">—</span>;
  const positive = val > 0;
  return (
    <span className={cn(
      "text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded",
      positive
        ? "text-emerald-300 bg-emerald-500/[0.07] border border-emerald-500/[0.15]"
        : "text-red-400/70 bg-red-400/[0.04] border border-red-400/[0.08]",
    )}>
      {positive ? "+" : ""}{val.toFixed(0)}pp
    </span>
  );
}

const PIP_LABELS = ["pos", "form", "H/A", "gd"] as const;
const PIP_TITLES: Record<string, string> = {
  "pos":  "Tabellposisjon og poeng",
  "form": "Løpsform (siste 5 kamper)",
  "H/A":  "Hjemme/Borte-rekord og snittmål",
  "gd":   "Målforskjell",
};

function DataCoveragePips({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-0.5 mt-[3px]">
      {PIP_LABELS.map((lbl, i) => (
        <div key={lbl} title={PIP_TITLES[lbl] ?? lbl} className={cn(
          "h-[3px] w-[10px] rounded-[1px]",
          i < score
            ? score === 4 ? "bg-emerald-500/50" : score >= 2 ? "bg-blue-500/30" : "bg-zinc-500/25"
            : "bg-[#1a1a1a]",
        )} />
      ))}
    </div>
  );
}

const COVERAGE_SYMBOL: Record<string, string> = {
  single: "", half_cover: "◐", full_cover: "●",
};
const COVERAGE_LABEL: Record<string, string> = {
  single: "Singel", half_cover: "Halvdekk", full_cover: "Heldekk",
};
const COVERAGE_COLOR: Record<string, string> = {
  single: "text-zinc-600", half_cover: "text-amber-600/60", full_cover: "text-emerald-600/70",
};

// ═══════════════════════════════════════════════════════════════════════════════
// TEAM COMPARISON CARD — FotMob/Opta-style football analytics
// ═══════════════════════════════════════════════════════════════════════════════

// ── Scoring helpers ───────────────────────────────────────────────────────────

function formScore(s: string | null, n = 5): number | null {
  if (!s) return null;
  const tail = s.toUpperCase().slice(-n);
  if (!tail.length) return null;
  const pts = [...tail].reduce((a, c) => a + (c === "W" ? 3 : c === "D" ? 1 : 0), 0);
  return Math.round((pts / (tail.length * 3)) * 100);
}

function recordScore(s: string | null): number | null {
  if (!s) return null;
  const w = parseInt(s.match(/W(\d+)/)?.[1] ?? "0");
  const d = parseInt(s.match(/D(\d+)/)?.[1] ?? "0");
  const l = parseInt(s.match(/L(\d+)/)?.[1] ?? "0");
  const total = w + d + l;
  return total > 0 ? Math.round(((3 * w + d) / (3 * total)) * 100) : null;
}

// ── Form pips — portal-based tooltip ─────────────────────────────────────────

function _resultLabel(c: string): string {
  return c === "W" ? "Seier" : c === "D" ? "Uavgjort" : "Tap";
}

function _resultTextCls(c: string): string {
  return c === "W" ? "text-emerald-400" : c === "D" ? "text-amber-400/80" : "text-red-400";
}

function _fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("nb-NO", { day: "numeric", month: "short" });
}

interface PipTooltipProps {
  c: string;
  match: RecentMatch | null | undefined;
  rect: DOMRect;
}

function PipTooltip({ c, match, rect }: PipTooltipProps) {
  const textCls = _resultTextCls(c);
  const score = match?.score_for != null && match?.score_against != null
    ? `${match.score_for}–${match.score_against}`
    : null;
  const venueLabel = match?.venue === "home" ? "Hjemme" : match?.venue === "away" ? "Borte" : null;
  const dateStr = match?.date ? _fmtDate(match.date) : null;

  const content = (
    <div
      style={{
        position: "fixed",
        left: rect.left + rect.width / 2,
        top: rect.top - 8,
        transform: "translateX(-50%) translateY(-100%)",
        zIndex: 9999,
        pointerEvents: "none",
        userSelect: "none",
      }}
    >
      <div className="bg-[#1c1c1c] border border-[#303030] rounded-md shadow-xl whitespace-nowrap overflow-hidden">
        {match && score ? (
          <div className="px-2.5 py-2 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className={cn("text-[11px] font-black leading-none", textCls)}>{c}</span>
              <span className="text-[10px] text-zinc-600">·</span>
              <span className={cn("text-[11px] font-bold tabular-nums leading-none", textCls)}>{score}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {match.opponent_logo && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={match.opponent_logo}
                  alt=""
                  width={12}
                  height={12}
                  className="object-contain shrink-0 opacity-80"
                />
              )}
              <span className="text-[9px] text-zinc-400 leading-none truncate max-w-[120px]">
                {match.opponent_name ?? "—"}
              </span>
            </div>
            {(venueLabel || dateStr) && (
              <div className="text-[8px] text-zinc-700 leading-none">
                {[venueLabel, dateStr].filter(Boolean).join(" · ")}
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5">
            <span className={cn("text-[10px] font-black leading-none tabular-nums", textCls)}>{c}</span>
            <span className="text-[9px] text-zinc-600 leading-none">·</span>
            <span className={cn("text-[10px] font-semibold leading-none", textCls)}>{_resultLabel(c)}</span>
          </div>
        )}
      </div>
      <div
        className="mx-auto"
        style={{
          width: 8,
          height: 4,
          background: "#303030",
          clipPath: "polygon(0 0, 100% 0, 50% 100%)",
        }}
      />
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(content, document.body);
}

function FormPips({ s, n = 5, withTooltips = false, recentMatches, align = "left" }: {
  s: string | null;
  n?: number;
  withTooltips?: boolean;
  recentMatches?: RecentMatch[] | null;
  align?: "left" | "right";
}) {
  const [hovered, setHovered] = useState<{ idx: number; rect: DOMRect } | null>(null);

  if (!s) return <span className="text-zinc-800 text-[9px]">—</span>;
  const tail = s.toUpperCase().slice(-n);

  if (!withTooltips) {
    return (
      <span className="flex items-center gap-1">
        {[...tail].map((c, i) => (
          <span
            key={i}
            title={_resultLabel(c)}
            className={cn(
              "inline-block w-[10px] h-[10px] rounded-full",
              c === "W" ? "bg-emerald-500" : c === "D" ? "bg-zinc-500" : "bg-red-500/60",
            )}
          />
        ))}
      </span>
    );
  }

  return (
    <>
      <span className={cn("flex items-center gap-[5px]", align === "right" && "flex-row-reverse")}>
        {[...tail].map((c, i) => {
          const dotCls = c === "W" ? "bg-emerald-500" : c === "D" ? "bg-zinc-500" : "bg-red-500/60";
          return (
            <span
              key={i}
              className="relative cursor-default"
              onMouseEnter={(e) =>
                setHovered({ idx: i, rect: e.currentTarget.getBoundingClientRect() })
              }
              onMouseLeave={() => setHovered(null)}
            >
              <span className={cn("inline-block w-[11px] h-[11px] rounded-full", dotCls)} />
            </span>
          );
        })}
      </span>
      {hovered !== null && (
        <PipTooltip
          c={tail[hovered.idx] ?? ""}
          match={recentMatches?.[hovered.idx]}
          rect={hovered.rect}
        />
      )}
    </>
  );
}

// ── Team logo ─────────────────────────────────────────────────────────────────

function TeamLogo({ url, name, size = 28 }: { url: string | null; name: string; size?: number }) {
  const sz = `${size}px`;
  if (!url) {
    return (
      <div
        className="rounded-xl bg-[#111] border border-[#1e1e1e] flex items-center justify-center shrink-0"
        style={{ width: sz, height: sz }}
      >
        <span
          className="font-bold text-zinc-700"
          style={{ fontSize: Math.max(8, Math.round(size * 0.28)) }}
        >
          {name.slice(0, 2).toUpperCase()}
        </span>
      </div>
    );
  }
  return (
    <img
      src={url}
      alt={name}
      width={size}
      height={size}
      className="object-contain shrink-0"
      style={{ width: sz, height: sz }}
      onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden"; }}
    />
  );
}

// ── Opta/FotMob position bar ──────────────────────────────────────────────────
// total: real league size from standings (null → show position only, no denominator)

function PositionBar({ position, total }: { position: number; total: number | null }) {
  const segments = Math.min(Math.max(total ?? position, position), 32);
  const quartile = position / segments;
  const currentColor =
    quartile <= 0.25 ? "rgba(16,185,129,0.90)"
    : quartile <= 0.5 ? "rgba(156,163,175,0.70)"
    : quartile <= 0.75 ? "rgba(120,113,108,0.60)"
    : "rgba(239,68,68,0.55)";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-end gap-[2px]">
        {Array.from({ length: segments }, (_, i) => {
          const rank = i + 1;
          const isCurrent = rank === position;
          const isAbove = rank < position;
          return (
            <div
              key={i}
              className="rounded-[1px] shrink-0"
              style={{
                width: 4,
                height: isCurrent ? 7 : 4,
                background: isCurrent ? currentColor : isAbove ? "rgba(60,60,60,0.60)" : "#1a1a1a",
              }}
            />
          );
        })}
      </div>
      <span className="text-[8px] text-zinc-600 tabular-nums leading-none">
        {position}.{total != null ? ` av ${total}` : ""}
      </span>
    </div>
  );
}

// ── Section group header ──────────────────────────────────────────────────────
// Amber accent dot + label + hairline rule — strong visual section anchor.

function GroupHeader({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 px-6 pt-5 pb-1">
      <span className="text-[8.5px] font-bold text-amber-500/75 uppercase tracking-[0.24em] shrink-0 leading-none">
        {label}
      </span>
      <div className="flex-1 h-px bg-[#1e1e1e]" />
    </div>
  );
}

// ── Premium stat row ──────────────────────────────────────────────────────────
// homeVal | LABEL | awayVal  with full-width share bar below.
// lowerIsBetter inverts the bar share so the defending side reads wider.
// signed=true → GD-style: color by sign, no comparison logic.

interface StatRowProps {
  label: string;
  homeText: string;
  awayText: string;
  homeRaw?: number | null;
  awayRaw?: number | null;
  lowerIsBetter?: boolean;
  noBar?: boolean;
  signed?: boolean;
}

function StatRow({
  label, homeText, awayText,
  homeRaw, awayRaw,
  lowerIsBetter = false,
  noBar = false,
  signed = false,
}: StatRowProps) {
  const both = homeRaw != null && awayRaw != null;

  // For signed rows (GD etc.) colour by sign, not comparison
  if (signed) {
    const signCls = (n: number | null) =>
      n == null ? "text-zinc-700"
      : n > 0    ? "text-emerald-400"
      : n < 0    ? "text-red-400/70"
      :             "text-zinc-500";
    return (
      <div className="py-2.5 border-b border-[#0f0f0f] last:border-0">
        <div className="grid grid-cols-[1fr_100px_1fr] items-center gap-2">
          <div className="text-right">
            <span className={cn("text-[16px] font-black tabular-nums leading-none tracking-tight", signCls(homeRaw ?? null))}>
              {homeText}
            </span>
          </div>
          <div className="text-[8px] font-bold text-zinc-600 uppercase tracking-[0.14em] text-center leading-snug px-1">
            {label}
          </div>
          <div>
            <span className={cn("text-[16px] font-black tabular-nums leading-none tracking-tight", signCls(awayRaw ?? null))}>
              {awayText}
            </span>
          </div>
        </div>
      </div>
    );
  }

  const homeWins = both ? (lowerIsBetter ? homeRaw! < awayRaw! : homeRaw! > awayRaw!) : false;
  const awayWins = both ? (lowerIsBetter ? awayRaw! < homeRaw! : awayRaw! > homeRaw!) : false;
  const hCls = homeWins ? "text-amber-400" : both ? "text-zinc-500" : "text-zinc-700";
  const aCls = awayWins ? "text-emerald-400" : both ? "text-zinc-500" : "text-zinc-700";

  // For the share bar: lowerIsBetter inverts so the winning (lower) side gets more bar.
  // Floor at 8%/ceiling at 92% prevents all-one-color bars when a value is 0.
  const rawH = both ? (lowerIsBetter ? awayRaw! : homeRaw!) : 0;
  const rawA = both ? (lowerIsBetter ? homeRaw! : awayRaw!) : 0;
  const rawTotal = rawH + rawA;
  const showBar = !noBar && both && rawTotal > 0;
  const hShare = showBar ? Math.max(0.08, Math.min(0.92, rawH / rawTotal)) : 0;
  const aShare = showBar ? 1 - hShare : 0;

  return (
    <div className="py-2.5 border-b border-[#0f0f0f] last:border-0">
      <div className="grid grid-cols-[1fr_100px_1fr] items-center gap-2">
        <div className="text-right">
          <span className={cn("text-[16px] font-black tabular-nums leading-none tracking-tight", hCls)}>
            {homeText}
          </span>
        </div>
        <div className="text-[8px] font-bold text-zinc-600 uppercase tracking-[0.14em] text-center leading-snug px-1">
          {label}
        </div>
        <div>
          <span className={cn("text-[16px] font-black tabular-nums leading-none tracking-tight", aCls)}>
            {awayText}
          </span>
        </div>
      </div>
      {showBar && (
        <div className="mt-[7px] flex h-[3px] rounded-full overflow-hidden">
          <div style={{
            flex: hShare,
            background: homeWins ? "rgba(245,158,11,0.52)" : "rgba(50,50,55,0.28)",
          }} />
          <div style={{
            flex: aShare,
            background: awayWins ? "rgba(16,185,129,0.48)" : "rgba(45,45,50,0.20)",
          }} />
        </div>
      )}
    </div>
  );
}

// ── Analyst signals — Norwegian football prose with team names ────────────────

interface Signal {
  text: string;
  side: "home" | "away" | "neutral";
}

function buildSignals(e: MatchEnrichment, homeTeam: string, awayTeam: string): Signal[] {
  const out: Signal[] = [];

  // Position
  if (e.home_position != null && e.away_position != null) {
    const diff = Math.abs(e.home_position - e.away_position);
    if (diff >= 3) {
      if (e.home_position < e.away_position) {
        out.push({
          text: `${homeTeam} er rangert ${e.home_position}. i ${e.league_name ?? "ligaen"}, klart over ${awayTeam} på ${e.away_position}. plass.`,
          side: "home",
        });
      } else {
        out.push({
          text: `${awayTeam} er høyest rangert i ${e.league_name ?? "ligaen"} (${e.away_position}.) — ${homeTeam} følger på ${e.home_position}. plass.`,
          side: "away",
        });
      }
    }
  }

  // Form (last 5)
  const hf5 = formScore(e.home_last_5);
  const af5 = formScore(e.away_last_5);
  if (hf5 != null && af5 != null && Math.abs(hf5 - af5) > 12) {
    const better = hf5 > af5 ? homeTeam : awayTeam;
    const bForm  = hf5 > af5 ? e.home_last_5?.slice(-5) : e.away_last_5?.slice(-5);
    const worse  = hf5 > af5 ? awayTeam : homeTeam;
    const wForm  = hf5 > af5 ? e.away_last_5?.slice(-5) : e.home_last_5?.slice(-5);
    out.push({
      text: `${better} er i bedre løpsform siste 5 kamper (${bForm}) enn ${worse} (${wForm}).`,
      side: hf5 > af5 ? "home" : "away",
    });
  }

  // Scoring
  const hGF = e.home_avg_goals_for;
  const aGF = e.away_avg_goals_for;
  if (hGF != null && aGF != null && Math.abs(hGF - aGF) > 0.35) {
    const better = hGF > aGF ? homeTeam : awayTeam;
    const worse  = hGF > aGF ? awayTeam : homeTeam;
    const high   = Math.max(hGF, aGF).toFixed(1);
    const low    = Math.min(hGF, aGF).toFixed(1);
    out.push({
      text: `${better} scorer ${high} mål per kamp i snitt — mer enn ${worse} (${low}).`,
      side: hGF > aGF ? "home" : "away",
    });
  }

  // Defence
  const hGA = e.home_avg_goals_against;
  const aGA = e.away_avg_goals_against;
  if (hGA != null && aGA != null && Math.abs(hGA - aGA) > 0.35 && out.length < 4) {
    const better = hGA < aGA ? homeTeam : awayTeam;
    const worse  = hGA < aGA ? awayTeam : homeTeam;
    const low    = Math.min(hGA, aGA).toFixed(1);
    const high   = Math.max(hGA, aGA).toFixed(1);
    out.push({
      text: `${better} slipper inn ${low} mål per kamp — langt bedre forsvar enn ${worse} (${high}).`,
      side: hGA < aGA ? "home" : "away",
    });
  }

  // H/A venue record
  const hr = recordScore(e.home_home_record);
  const ar = recordScore(e.away_away_record);
  if (hr != null && ar != null && Math.abs(hr - ar) > 15 && out.length < 4) {
    if (hr > ar) {
      const rec = e.home_home_record?.replace(/([WDL])(\d+)/g, "$1$2 ").trim();
      out.push({ text: `${homeTeam} er sterk på hjemmebane denne sesongen (${rec}).`, side: "home" });
    } else {
      const rec = e.away_away_record?.replace(/([WDL])(\d+)/g, "$1$2 ").trim();
      out.push({ text: `${awayTeam} er sterk på bortebane denne sesongen (${rec}).`, side: "away" });
    }
  }

  // Conflict — high rank but poor form
  if (
    e.home_position != null && e.away_position != null &&
    hf5 != null && af5 != null &&
    (e.home_position < e.away_position) !== (hf5 > af5) &&
    Math.abs(hf5 - af5) > 18 &&
    out.length < 4
  ) {
    const ranked = e.home_position < e.away_position ? homeTeam : awayTeam;
    const formed = hf5 > af5 ? homeTeam : awayTeam;
    if (ranked !== formed) {
      out.push({
        text: `${ranked} er rangert høyest, men ${formed} er i klart bedre løpsform — tabellplassering og momentumet peker i hver sin retning.`,
        side: "neutral",
      });
    }
  }

  return out.slice(0, 4);
}

// ── TeamComparisonCard — main expanded card ───────────────────────────────────

function TeamComparisonCard({
  match, enrichment, colSpan,
}: {
  match: MatchResult;
  enrichment: MatchEnrichment | null;
  colSpan: number;
}) {
  const hasData = enrichment?.has_api_football_data ?? false;
  const e = enrichment;
  const hFS = e?.home_recent_fixture_stats ?? null;
  const aFS = e?.away_recent_fixture_stats ?? null;
  const hasFixStats = hFS != null || aFS != null;

  const hGF  = hasData ? e!.home_goals_for   : null;
  const hGA  = hasData ? e!.home_goals_against : null;
  const aGF  = hasData ? e!.away_goals_for   : null;
  const aGA  = hasData ? e!.away_goals_against : null;
  const hGD  = hGF != null && hGA != null ? hGF - hGA : null;
  const aGD  = aGF != null && aGA != null ? aGF - aGA : null;

  const hAvgGF = hasData ? e!.home_avg_goals_for    : null;
  const aAvgGF = hasData ? e!.away_avg_goals_for    : null;
  const hAvgGA = hasData ? e!.home_avg_goals_against : null;
  const aAvgGA = hasData ? e!.away_avg_goals_against : null;

  const leagueSize = hasData ? (e!.league_size ?? null) : null;

  const signals = hasData ? buildSignals(e!, match.home_team, match.away_team) : [];

  const wdlStr = (w: number | null, d: number | null, l: number | null) =>
    w != null && d != null && l != null ? `${w}–${d}–${l}` : "—";

  const recordStr = (s: string | null) => {
    if (!s) return "—";
    const w = s.match(/W(\d+)/i);
    const d = s.match(/D(\d+)/i);
    const l = s.match(/L(\d+)/i);
    return (w && d && l) ? `${w[1]}–${d[1]}–${l[1]}` : s;
  };

  const hRec = recordScore(hasData ? e!.home_home_record : null);
  const aRec = recordScore(hasData ? e!.away_away_record : null);

  // Count venue-specific games played to suppress 0-game rows (WC teams often
  // play 0 "home" fixtures in a tournament — showing 0.0 avg would mislead).
  const venueGames = (s: string | null): number => {
    if (!s) return 0;
    const w = parseInt(s.match(/W(\d+)/i)?.[1] ?? "0");
    const d = parseInt(s.match(/D(\d+)/i)?.[1] ?? "0");
    const l = parseInt(s.match(/L(\d+)/i)?.[1] ?? "0");
    return w + d + l;
  };
  const hHomeGames = hasData ? venueGames(e!.home_home_record) : 0;
  const aAwayGames = hasData ? venueGames(e!.away_away_record) : 0;
  // Only show venue-specific goals/clean-sheets when at least one side has played > 0 games there.
  // Guard all with hasData to avoid e! access when enrichment is null.
  const hasVenueGoals = hasData && (
    (e!.home_avg_goals_for_home != null && hHomeGames > 0)
    || (e!.away_avg_goals_for_away != null && aAwayGames > 0)
  );
  const hasVenueConceded = hasData && (
    (e!.home_avg_goals_against_home != null && hHomeGames > 0)
    || (e!.away_avg_goals_against_away != null && aAwayGames > 0)
  );
  const hasVenueCS = hasData && (
    (e!.home_clean_sheets_home != null && hHomeGames > 0)
    || (e!.away_clean_sheets_away != null && aAwayGames > 0)
  );

  return (
    <tr>
      <td colSpan={colSpan} className="p-0 border-b border-[#1a1a1a]">
        <div className="animate-expand-down bg-[#070707] border-t border-[#1e1e1e]">

          {/* ── HEADER: logos + team names + form + position ──────────────── */}
          <div className="grid grid-cols-2 divide-x divide-[#1a1a1a] px-0 pt-5 pb-4">

            {/* Home */}
            <div className="px-5 flex items-start gap-3">
              <TeamLogo url={e?.home_logo_url ?? null} name={match.home_team} size={44} />
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="text-[14px] font-black leading-tight tracking-tight text-zinc-100">
                  {match.home_team}
                </div>
                <div className="text-[8px] text-zinc-700 uppercase tracking-[0.1em] mt-0.5">
                  Hjemme{e?.league_name ? ` · ${e.league_name}` : ""}
                </div>
                {hasData && e!.home_last_5 && (
                  <div className="mt-2">
                    <FormPips
                      s={e!.home_last_5}
                      n={5}
                      withTooltips
                      recentMatches={e!.home_recent_matches}
                      align="left"
                    />
                  </div>
                )}
                {hasData && e!.home_position != null && (
                  <div className="mt-2">
                    <PositionBar position={e!.home_position} total={leagueSize} />
                  </div>
                )}
              </div>
            </div>

            {/* Away */}
            <div className="px-5 flex items-start justify-end gap-3">
              <div className="min-w-0 text-right flex-1 pt-0.5">
                <div className="text-[14px] font-black leading-tight tracking-tight text-zinc-100">
                  {match.away_team}
                </div>
                <div className="text-[8px] text-zinc-700 uppercase tracking-[0.1em] mt-0.5">
                  Borte{e?.league_name ? ` · ${e.league_name}` : ""}
                </div>
                {hasData && e!.away_last_5 && (
                  <div className="mt-2 flex justify-end">
                    <FormPips
                      s={e!.away_last_5}
                      n={5}
                      withTooltips
                      recentMatches={e!.away_recent_matches}
                      align="right"
                    />
                  </div>
                )}
                {hasData && e!.away_position != null && (
                  <div className="mt-2 flex justify-end">
                    <PositionBar position={e!.away_position} total={leagueSize} />
                  </div>
                )}
              </div>
              <TeamLogo url={e?.away_logo_url ?? null} name={match.away_team} size={44} />
            </div>
          </div>

          {/* ── STATS: grouped sections (TABELL / ANGREP+FORSVAR / REKORD) ── */}
          {hasData ? (
            <>
              {/* ── TABELL ─────────────────────────────────────────────────── */}
              {(e!.home_position != null || e!.away_position != null ||
                e!.home_points != null || e!.away_points != null ||
                e!.home_wins != null || hGD != null) && (
                <>
                  <GroupHeader label="Tabell" />
                  <div className="px-6 pb-1">
                    {(e!.home_position != null || e!.away_position != null) && (
                      <StatRow
                        label="Posisjon"
                        homeText={e!.home_position != null ? `${e!.home_position}.` : "—"}
                        awayText={e!.away_position != null ? `${e!.away_position}.` : "—"}
                        homeRaw={e!.home_position}
                        awayRaw={e!.away_position}
                        lowerIsBetter
                      />
                    )}
                    {(e!.home_points != null || e!.away_points != null) && (
                      <StatRow
                        label="Poeng"
                        homeText={e!.home_points != null ? String(e!.home_points) : "—"}
                        awayText={e!.away_points != null ? String(e!.away_points) : "—"}
                        homeRaw={e!.home_points}
                        awayRaw={e!.away_points}
                      />
                    )}
                    {(e!.home_wins != null || e!.away_wins != null) && (
                      <StatRow
                        label="S – U – T"
                        homeText={wdlStr(e!.home_wins, e!.home_draws, e!.home_losses)}
                        awayText={wdlStr(e!.away_wins, e!.away_draws, e!.away_losses)}
                        homeRaw={e!.home_wins}
                        awayRaw={e!.away_wins}
                        noBar
                      />
                    )}
                    {(hGD != null || aGD != null) && (
                      <StatRow
                        label="Målforskjell"
                        homeText={hGD != null ? (hGD > 0 ? `+${hGD}` : `${hGD}`) : "—"}
                        awayText={aGD != null ? (aGD > 0 ? `+${aGD}` : `${aGD}`) : "—"}
                        homeRaw={hGD}
                        awayRaw={aGD}
                        signed
                      />
                    )}
                  </div>
                </>
              )}

              {/* ── ANGREP / FORSVAR ───────────────────────────────────────── */}
              {(hAvgGF != null || aAvgGF != null ||
                hAvgGA != null || aAvgGA != null ||
                e!.home_clean_sheets != null || e!.away_clean_sheets != null) && (
                <>
                  <GroupHeader label="Angrep / Forsvar" />
                  <div className="px-6 pb-1">
                    {(hAvgGF != null || aAvgGF != null) && (
                      <StatRow
                        label="Mål / kamp"
                        homeText={hAvgGF != null ? hAvgGF.toFixed(1) : "—"}
                        awayText={aAvgGF != null ? aAvgGF.toFixed(1) : "—"}
                        homeRaw={hAvgGF}
                        awayRaw={aAvgGF}
                      />
                    )}
                    {(hAvgGA != null || aAvgGA != null) && (
                      <StatRow
                        label="Innsluppet"
                        homeText={hAvgGA != null ? hAvgGA.toFixed(1) : "—"}
                        awayText={aAvgGA != null ? aAvgGA.toFixed(1) : "—"}
                        homeRaw={hAvgGA}
                        awayRaw={aAvgGA}
                        lowerIsBetter
                      />
                    )}
                    {(e!.home_clean_sheets != null || e!.away_clean_sheets != null) && (
                      <StatRow
                        label="Nullhold."
                        homeText={e!.home_clean_sheets != null ? String(e!.home_clean_sheets) : "—"}
                        awayText={e!.away_clean_sheets != null ? String(e!.away_clean_sheets) : "—"}
                        homeRaw={e!.home_clean_sheets}
                        awayRaw={e!.away_clean_sheets}
                      />
                    )}
                  </div>
                </>
              )}

              {/* ── HJEMME / BORTE ────────────────────────────────────────── */}
              {(e!.home_home_record || e!.away_away_record || hasVenueGoals) && (
                <>
                  <GroupHeader label="Hjemme / Borte" />
                  <div className="px-6 pb-1">
                    {(e!.home_home_record || e!.away_away_record) && (
                      <StatRow
                        label="Rekord"
                        homeText={recordStr(e!.home_home_record)}
                        awayText={recordStr(e!.away_away_record)}
                        homeRaw={hRec}
                        awayRaw={aRec}
                        noBar
                      />
                    )}
                    {hasVenueGoals && (
                      <StatRow
                        label="Mål / kamp"
                        homeText={hHomeGames > 0 && e!.home_avg_goals_for_home != null ? e!.home_avg_goals_for_home.toFixed(1) : "—"}
                        awayText={aAwayGames > 0 && e!.away_avg_goals_for_away != null ? e!.away_avg_goals_for_away.toFixed(1) : "—"}
                        homeRaw={hHomeGames > 0 ? e!.home_avg_goals_for_home : null}
                        awayRaw={aAwayGames > 0 ? e!.away_avg_goals_for_away : null}
                      />
                    )}
                    {hasVenueConceded && (
                      <StatRow
                        label="Innsluppet"
                        homeText={hHomeGames > 0 && e!.home_avg_goals_against_home != null ? e!.home_avg_goals_against_home.toFixed(1) : "—"}
                        awayText={aAwayGames > 0 && e!.away_avg_goals_against_away != null ? e!.away_avg_goals_against_away.toFixed(1) : "—"}
                        homeRaw={hHomeGames > 0 ? e!.home_avg_goals_against_home : null}
                        awayRaw={aAwayGames > 0 ? e!.away_avg_goals_against_away : null}
                        lowerIsBetter
                      />
                    )}
                    {hasVenueCS && (
                      <StatRow
                        label="Nullhold."
                        homeText={hHomeGames > 0 && e!.home_clean_sheets_home != null ? String(e!.home_clean_sheets_home) : "—"}
                        awayText={aAwayGames > 0 && e!.away_clean_sheets_away != null ? String(e!.away_clean_sheets_away) : "—"}
                        homeRaw={hHomeGames > 0 ? e!.home_clean_sheets_home : null}
                        awayRaw={aAwayGames > 0 ? e!.away_clean_sheets_away : null}
                      />
                    )}
                  </div>
                </>
              )}

              <div className="pb-3" />
            </>
          ) : (
            <div className="px-6 py-8 text-center">
              <p className="text-[10px] text-zinc-800 italic">
                Ingen statistikk tilgjengelig for dette oppgjøret
              </p>
            </div>
          )}

          {/* ── TOPPSTATISTIKK: aggregated from /fixtures/statistics ───────── */}
          {hasFixStats && (() => {
            const fmt1 = (v: number | null) => v != null ? v.toFixed(1) : "—";
            const fmtPct = (v: number | null) => v != null ? `${v.toFixed(0)}%` : "—";
            const fmtXg = (v: number | null) => v != null ? v.toFixed(2) : "—";
            const sampleNote = (() => {
              const n = Math.min(hFS?.sample_size ?? Infinity, aFS?.sample_size ?? Infinity);
              if (n === Infinity) return null;
              return n <= 2 ? `basert på ${n} kamp${n === 1 ? "" : "er"}` : null;
            })();

            const rows: Array<{ label: string; hVal: string; aVal: string; hRaw: number | null; aRaw: number | null; lowerIsBetter?: boolean }> = [];

            if (hFS?.avg_possession != null || aFS?.avg_possession != null)
              rows.push({ label: "Ballbesittelse", hVal: fmtPct(hFS?.avg_possession ?? null), aVal: fmtPct(aFS?.avg_possession ?? null), hRaw: hFS?.avg_possession ?? null, aRaw: aFS?.avg_possession ?? null });
            if (hFS?.avg_total_shots != null || aFS?.avg_total_shots != null)
              rows.push({ label: "Skudd", hVal: fmt1(hFS?.avg_total_shots ?? null), aVal: fmt1(aFS?.avg_total_shots ?? null), hRaw: hFS?.avg_total_shots ?? null, aRaw: aFS?.avg_total_shots ?? null });
            if (hFS?.avg_shots_on_goal != null || aFS?.avg_shots_on_goal != null)
              rows.push({ label: "Skudd på mål", hVal: fmt1(hFS?.avg_shots_on_goal ?? null), aVal: fmt1(aFS?.avg_shots_on_goal ?? null), hRaw: hFS?.avg_shots_on_goal ?? null, aRaw: aFS?.avg_shots_on_goal ?? null });
            if (hFS?.avg_corners != null || aFS?.avg_corners != null)
              rows.push({ label: "Cornere", hVal: fmt1(hFS?.avg_corners ?? null), aVal: fmt1(aFS?.avg_corners ?? null), hRaw: hFS?.avg_corners ?? null, aRaw: aFS?.avg_corners ?? null });
            if (hFS?.avg_pass_accuracy != null || aFS?.avg_pass_accuracy != null)
              rows.push({ label: "Pasninger %", hVal: fmtPct(hFS?.avg_pass_accuracy ?? null), aVal: fmtPct(aFS?.avg_pass_accuracy ?? null), hRaw: hFS?.avg_pass_accuracy ?? null, aRaw: aFS?.avg_pass_accuracy ?? null });
            if (hFS?.avg_fouls != null || aFS?.avg_fouls != null)
              rows.push({ label: "Frispark", hVal: fmt1(hFS?.avg_fouls ?? null), aVal: fmt1(aFS?.avg_fouls ?? null), hRaw: hFS?.avg_fouls ?? null, aRaw: aFS?.avg_fouls ?? null, lowerIsBetter: true });
            if (hFS?.avg_yellow_cards != null || aFS?.avg_yellow_cards != null)
              rows.push({ label: "Gule kort", hVal: fmt1(hFS?.avg_yellow_cards ?? null), aVal: fmt1(aFS?.avg_yellow_cards ?? null), hRaw: hFS?.avg_yellow_cards ?? null, aRaw: aFS?.avg_yellow_cards ?? null, lowerIsBetter: true });
            if (hFS?.avg_xg != null || aFS?.avg_xg != null)
              rows.push({ label: "Forventa mål (xG)", hVal: fmtXg(hFS?.avg_xg ?? null), aVal: fmtXg(aFS?.avg_xg ?? null), hRaw: hFS?.avg_xg ?? null, aRaw: aFS?.avg_xg ?? null });

            if (rows.length === 0) return null;

            return (
              <>
                <GroupHeader label="Toppstatistikk" />
                <div className="px-6 pb-1">
                  {rows.map((row) => (
                    <StatRow
                      key={row.label}
                      label={row.label}
                      homeText={row.hVal}
                      awayText={row.aVal}
                      homeRaw={row.hRaw}
                      awayRaw={row.aRaw}
                      lowerIsBetter={row.lowerIsBetter}
                    />
                  ))}
                  {sampleNote && (
                    <div className="pt-2 pb-1 text-right">
                      <span className="text-[8px] text-zinc-800 italic">{sampleNote}</span>
                    </div>
                  )}
                </div>
                <div className="pb-2" />
              </>
            );
          })()}

          {/* ── ANALYSE: Norwegian football prose ──────────────────────────── */}
          {signals.length > 0 && (
            <>
              <GroupHeader label="Analyse" />
              <div className="px-6 pb-5 pt-2 space-y-3">
                {signals.map((sig, i) => (
                  <div key={i} className="flex gap-3 items-start">
                    <div
                      className={cn(
                        "w-[2px] shrink-0 rounded-full self-stretch mt-[2px]",
                        sig.side === "home"
                          ? "bg-amber-500/55"
                          : sig.side === "away"
                          ? "bg-emerald-600/55"
                          : "bg-zinc-700/35",
                      )}
                      style={{ minHeight: 14 }}
                    />
                    <p className="text-[11px] text-zinc-400 leading-relaxed">{sig.text}</p>
                  </div>
                ))}
              </div>
            </>
          )}

        </div>
      </td>
    </tr>
  );
}

// ── Skeleton row ──────────────────────────────────────────────────────────────

function SkeletonRow({ i }: { i: number }) {
  return (
    <tr className="border-b border-[#1a1a1a]" style={{ animationDelay: `${i * 35}ms` }}>
      <td className="py-2.5 px-3"><div className="skeleton h-3 w-4 rounded" /></td>
      <td className="py-2.5 px-3">
        <div className="space-y-1.5">
          <div className="skeleton h-3 rounded" style={{ width: `${58 + (i * 19) % 28}%` }} />
          <div className="skeleton h-2.5 w-20 rounded" />
        </div>
      </td>
      {[64, 120, 110, 76, 52, 40, 40, 24].map((w, j) => (
        <td key={j} className="py-2.5 px-3">
          <div className="skeleton h-3 rounded mx-auto" style={{ width: w * 0.55 }} />
        </td>
      ))}
    </tr>
  );
}

// ── Match row ─────────────────────────────────────────────────────────────────

function MatchRow({
  match, enrichment, index, isExpanded, onToggle,
}: {
  match: MatchResult;
  enrichment: MatchEnrichment | null;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const isConviction = match.is_conviction;
  const picks = match.picks;
  const barDelay = index * 35;

  const crowd = match.has_public_tips
    ? [
        { label: "H", v: match.pub_prob_h ?? 0 },
        { label: "U", v: match.pub_prob_u ?? 0 },
        { label: "B", v: match.pub_prob_b ?? 0 },
      ]
    : null;

  return (
    <>
      <tr
        className={cn(
          "border-b border-[#1a1a1a] transition-colors duration-100 animate-fade-up group cursor-pointer",
          isExpanded
            ? "bg-[#0e0e0e]"
            : isConviction
            ? "hover:bg-amber-400/[0.025]"
            : "hover:bg-white/[0.015]",
        )}
        style={{ animationDelay: `${index * 38}ms` }}
        onClick={onToggle}
      >
        {/* # */}
        <td className="py-2.5 pl-4 pr-2 w-8">
          <span className="text-[10px] text-zinc-700 tabular-nums font-medium">
            {match.match_number}
          </span>
        </td>

        {/* Teams */}
        <td className="py-2.5 px-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className={cn("shrink-0 transition-opacity", isConviction ? "opacity-100" : "opacity-0")}>
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inset-0 rounded-full bg-amber-400 animate-ping opacity-35" />
                <span className="relative rounded-full h-1.5 w-1.5 bg-amber-400" />
              </span>
            </span>
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-zinc-200 truncate leading-snug">
                {match.home_team}
              </div>
              <div className="flex items-center gap-1 mt-0.5">
                <span className="text-[9px] font-semibold text-zinc-700 uppercase tracking-wider">vs</span>
                <span className="text-[10px] text-zinc-600 truncate">{match.away_team}</span>
              </div>
              <DataCoveragePips score={match.data_coverage} />
            </div>
          </div>
        </td>

        {/* Pick + coverage */}
        <td className="py-2.5 px-3 w-28">
          <div className="flex flex-col items-center gap-1">
            <div className={cn(
              "inline-flex items-center px-2.5 py-1.5 rounded-lg border",
              isConviction
                ? "border-amber-400/20 bg-amber-400/[0.03]"
                : "border-[#252525] bg-[#161616]",
            )}>
              <span className="text-[13px] font-black tracking-wider text-zinc-100 whitespace-nowrap">
                {picks.join(" · ")}
              </span>
            </div>
            <div className={cn(
              "text-[9px] font-semibold uppercase tracking-wider",
              COVERAGE_COLOR[match.coverage_type],
            )}>
              {COVERAGE_SYMBOL[match.coverage_type]
                ? `${COVERAGE_SYMBOL[match.coverage_type]} `
                : ""}
              {COVERAGE_LABEL[match.coverage_type]}
            </div>
          </div>
        </td>

        {/* Model probabilities */}
        <td className="py-2.5 px-3 w-44">
          <div className="flex flex-col gap-[3px]">
            <ProbBar label="H" value={match.prob_h} highlighted={match.recommendation === "H"} delay={barDelay} />
            <ProbBar label="U" value={match.prob_u} highlighted={match.recommendation === "U"} delay={barDelay + 80} />
            <ProbBar label="B" value={match.prob_b} highlighted={match.recommendation === "B"} delay={barDelay + 160} />
          </div>
        </td>

        {/* Crowd */}
        <td className="py-2.5 px-3 w-20">
          {crowd ? (
            <div className="flex flex-col gap-[3px]">
              {crowd.map(({ label, v }) => (
                <div key={label} className="flex items-center gap-1.5">
                  <span className="text-[10px] text-zinc-700 w-3 text-right shrink-0 font-medium">{label}</span>
                  <span className={cn(
                    "text-[10px] tabular-nums font-semibold",
                    label === match.recommendation ? "text-zinc-300" : "text-zinc-700",
                  )}>
                    {Math.round(v * 100)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-[10px] text-zinc-800">—</span>
          )}
        </td>

        {/* Edge */}
        <td className="py-2.5 px-3 text-right w-16"><EdgeBadge match={match} /></td>

        {/* VI */}
        <td className="py-2.5 px-3 text-center w-14"><ViBadge vi={match.vi} /></td>

        {/* CDS */}
        <td className="py-2.5 px-3 text-center w-16"><CdsBadge cds={match.crowd_disagreement_score} /></td>

        {/* Expand toggle */}
        <td className="py-2.5 pr-3 pl-1 w-28">
          <span className={cn(
            "inline-flex items-center gap-1 text-[10px] transition-colors select-none",
            isExpanded ? "text-zinc-300" : "text-zinc-500 group-hover:text-zinc-300",
          )}>
            <span>{isExpanded ? "▴" : "▾"}</span>
            <span>{isExpanded ? "Lukk" : "Analyse"}</span>
          </span>
        </td>
      </tr>

      {isExpanded && (
        <TeamComparisonCard match={match} enrichment={enrichment} colSpan={9} />
      )}
    </>
  );
}

// ── Match table ───────────────────────────────────────────────────────────────

interface MatchTableProps {
  matches: MatchResult[];
  enrichmentMap?: Map<number, MatchEnrichment>;
  isLoading?: boolean;
}

const TH = "text-[9px] font-bold text-zinc-700 uppercase tracking-[1.2px] py-2.5 px-3 whitespace-nowrap";

export function MatchTable({ matches, enrichmentMap, isLoading }: MatchTableProps) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);

  function toggleRow(num: number) {
    setExpandedRow((prev) => (prev === num ? null : num));
  }

  return (
    <div className="rounded-xl border border-[#202020] bg-[#101010] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[#202020]" style={{ background: "#0a0a0a" }}>
              <th className={cn(TH, "pl-4 pr-2 text-left w-8")}>#</th>
              <th className={cn(TH, "text-left")}>Kamp</th>
              <th className={cn(TH, "text-center w-28")}>Pick</th>
              <th className={cn(TH, "text-left w-44")} title="Modellens H/U/B-sannsynligheter basert på bookmakerprior og API-Football-statistikk">Modell</th>
              <th className={cn(TH, "text-left w-20")} title="Norsk Tippings folkeprosent — offentlig mening fra nt.no, fryst ved siste synkronisering">Folket</th>
              <th className={cn(TH, "text-right w-16")} title="Edge — modellsannsynlighet minus folkets sannsynlighet (prosentpoeng). Positivt er fordel.">Edge</th>
              <th className={cn(TH, "text-center w-14")} title="VI (Value Index) — modellsannsynlighet ÷ odds-implisert sannsynlighet. Over 1,0 betyr at modellen ser mer verdi enn markedet.">VI</th>
              <th className={cn(TH, "text-center w-16")} title="CDS (Crowd Disagreement Score) — differanse mellom modell og folk i prosentpoeng. Høy CDS = potensiell pool-edge.">CDS</th>
              <th className={cn(TH, "text-left w-28 pr-3")}>Analyse</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 12 }, (_, i) => <SkeletonRow key={i} i={i} />)
              : matches.map((m, i) => (
                  <MatchRow
                    key={m.match_number}
                    match={m}
                    enrichment={enrichmentMap?.get(m.match_number) ?? null}
                    index={i}
                    isExpanded={expandedRow === m.match_number}
                    onToggle={() => toggleRow(m.match_number)}
                  />
                ))}
          </tbody>
        </table>
      </div>

      {!isLoading && matches.length === 0 && (
        <div className="py-16 text-center text-zinc-700 text-sm">
          Ingen kamper tilgjengelig
        </div>
      )}
    </div>
  );
}
