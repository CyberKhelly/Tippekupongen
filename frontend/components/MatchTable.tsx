"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { cn, recValue, sortSigns } from "@/lib/utils";
import type { MatchEnrichment, MatchResult, RecentMatch } from "@/lib/types";

// ── Outcome colors (light-mode) ───────────────────────────────────────────────

const PROB_COLORS: Record<string, string> = {
  H: "#6098F2",
  U: "#7A7673",
  B: "#34D399",
};

// ── Signature: Pick Tile ──────────────────────────────────────────────────────

function PickTile({
  pick,
  isPrimary,
  isConviction,
  size = 32,
}: {
  pick: string;
  isPrimary: boolean;
  isConviction: boolean;
  size?: number;
}) {
  const isGold = isPrimary && isConviction;
  const isDark = isPrimary && !isConviction;
  const bg     = isGold ? "#F5C030" : isDark ? "#E8E4DD" : "#1C1C1C";
  const border = isGold || isDark ? "none" : "1.5px solid rgba(255,255,255,0.1)";
  const color  = isGold ? "#0D0D0D" : isDark ? "#0D0D0D" : "#4A4744";
  const fs     = size >= 30 ? 14 : size >= 26 ? 12 : 11;

  return (
    <div
      style={{
        width: size, height: size, borderRadius: 4,
        background: bg, border,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0,
      }}
    >
      <span style={{ fontSize: fs, fontWeight: 700, color, letterSpacing: "0.04em", lineHeight: 1 }}>
        {pick}
      </span>
    </div>
  );
}

// ── Prob bar ──────────────────────────────────────────────────────────────────

function ProbBar({
  label, value, highlighted, delay,
}: { label: string; value: number; highlighted: boolean; delay: number }) {
  const pct   = Math.round(value * 100);
  const color = PROB_COLORS[label] ?? "#9B9894";
  return (
    <div className="flex items-center gap-1.5 min-w-0">
      <span className={cn(
        "text-[10px] w-3 text-right shrink-0 tabular-nums font-semibold",
        highlighted ? "text-[#7A7673]" : "text-[#4A4744]",
      )}>
        {label}
      </span>
      <div className="flex-1 h-[3px] rounded-full overflow-hidden min-w-[36px]" style={{ background: "rgba(255,255,255,0.06)" }}>
        <div
          className="h-full rounded-full animate-bar-grow"
          style={{
            width: `${pct}%`,
            backgroundColor: color,
            opacity: highlighted ? 1 : 0.20,
            transformOrigin: "left",
            animationDelay: `${delay}ms`,
          }}
        />
      </div>
      <span className={cn(
        "text-[10px] tabular-nums w-6 text-right shrink-0 font-medium",
        highlighted ? "text-[#E8E4DD]" : "text-[#4A4744]",
      )}>
        {pct}%
      </span>
    </div>
  );
}

// ── Badges ────────────────────────────────────────────────────────────────────

function CdsBadge({ cds }: { cds: number | null }) {
  if (cds == null) return <span className="text-[10px] text-[#4A4744]">—</span>;
  const level = cds >= 20 ? "high" : cds >= 10 ? "mid" : "low";
  const cls = {
    high: "text-[#F5C030] bg-[rgba(245,192,48,0.12)] border border-[rgba(245,192,48,0.2)]",
    mid:  "text-[#7A7673] bg-[#1C1C1C] border border-[rgba(255,255,255,0.1)]",
    low:  "text-[#4A4744]",
  }[level];
  return (
    <span className={cn("text-[10px] tabular-nums font-semibold px-1.5 py-0.5 rounded", cls)}>
      {cds.toFixed(1)}
    </span>
  );
}

function ViBadge({ vi }: { vi: number | null }) {
  if (vi == null) return <span className="text-[10px] text-[#4A4744]">—</span>;
  const isHigh  = vi >= 1.2;
  const isAbove = vi > 1.0;
  // indigo for crowd-overvalued (vi < 1.0) — not a failure, just a counter-signal
  const color = isHigh ? "text-[#5FAE6E]" : isAbove ? "text-[#E8E4DD]" : "text-[#7B92FF]";
  return (
    <span className={cn("text-[10px] tabular-nums font-bold", color)}>
      {vi.toFixed(2)}
      <span className="text-[8px] ml-0.5 opacity-50">{isAbove ? "↑" : "↓"}</span>
    </span>
  );
}

function EdgeBadge({ match }: { match: MatchResult }) {
  if (!match.has_public_tips) return <span className="text-[10px] text-[#4A4744]">—</span>;
  const val = recValue(match.recommendation, match.value_h, match.value_u, match.value_b);
  if (val == null) return <span className="text-[10px] text-[#4A4744]">—</span>;
  const positive = val > 0;
  const abs = Math.abs(val);
  return (
    <span
      className="text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded"
      style={positive
        ? { color: "#5FAE6E", background: "rgba(95,174,110,0.12)", border: "1px solid rgba(95,174,110,0.2)" }
        : { color: "#7B92FF", background: "rgba(123,146,255,0.10)", border: "1px solid rgba(123,146,255,0.20)" }
      }
    >
      {positive ? "+" : "≠"}{abs.toFixed(0)}pp
    </span>
  );
}

// ── Small team logo ───────────────────────────────────────────────────────────

function SmallLogo({ url, name }: { url: string | null | undefined; name: string }) {
  if (!url) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={url} alt={name} width={18} height={18}
      className="object-contain shrink-0"
      style={{ width: 18, height: 18 }}
      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
    />
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// EXPANDED CARD
// ═══════════════════════════════════════════════════════════════════════════════

function formScore(s: string | null, n = 5): number | null {
  if (!s) return null;
  const tail = s.toUpperCase().slice(-n);
  if (!tail.length) return null;
  const pts = [...tail].reduce((a, c) => a + (c === "W" ? 3 : c === "D" ? 1 : 0), 0);
  return Math.round((pts / (tail.length * 3)) * 100);
}

function recordScore(s: string | null): number | null {
  if (!s) return null;
  const w = parseInt(s.match(/W(\d+)/i)?.[1] ?? "0");
  const d = parseInt(s.match(/D(\d+)/i)?.[1] ?? "0");
  const l = parseInt(s.match(/L(\d+)/i)?.[1] ?? "0");
  const total = w + d + l;
  return total > 0 ? Math.round(((3 * w + d) / (3 * total)) * 100) : null;
}

// ── Tooltip (dark on light page) ──────────────────────────────────────────────

function _resultLabel(c: string) { return c === "W" ? "Seier" : c === "D" ? "Uavgjort" : "Tap"; }
function _resultColor(c: string) { return c === "W" ? "#16A34A" : c === "D" ? "#D4930A" : "#EF4444"; }
function _fmtDate(iso: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleDateString("nb-NO", { day: "numeric", month: "short" });
}

function PipTooltip({ c, match, rect }: { c: string; match: RecentMatch | null | undefined; rect: DOMRect }) {
  const score = match?.score_for != null ? `${match.score_for}–${match.score_against}` : null;
  const venue = match?.venue === "home" ? "Hjemme" : match?.venue === "away" ? "Borte" : null;
  const date  = match?.date ? _fmtDate(match.date) : null;
  const col   = _resultColor(c);

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
      <div className="bg-[#111110] rounded-lg shadow-elevated whitespace-nowrap overflow-hidden">
        {match && score ? (
          <div className="px-2.5 py-2 space-y-1">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-black leading-none" style={{ color: col }}>{c}</span>
              <span className="text-[10px] text-white/30">·</span>
              <span className="text-[11px] font-bold tabular-nums leading-none" style={{ color: col }}>{score}</span>
            </div>
            <div className="flex items-center gap-1.5">
              {match.opponent_logo && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={match.opponent_logo} alt="" width={12} height={12} className="object-contain shrink-0 opacity-70" />
              )}
              <span className="text-[9px] text-white/50 leading-none truncate max-w-[120px]">{match.opponent_name ?? "—"}</span>
            </div>
            {(venue || date) && (
              <div className="text-[8px] text-white/30 leading-none">{[venue, date].filter(Boolean).join(" · ")}</div>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-2.5 py-1.5">
            <span className="text-[10px] font-black leading-none" style={{ color: col }}>{c}</span>
            <span className="text-[9px] text-white/40">·</span>
            <span className="text-[10px] font-semibold text-white/70 leading-none">{_resultLabel(c)}</span>
          </div>
        )}
      </div>
      <div className="mx-auto" style={{ width: 8, height: 4, background: "#111110", clipPath: "polygon(0 0, 100% 0, 50% 100%)" }} />
    </div>
  );

  if (typeof document === "undefined") return null;
  return createPortal(content, document.body);
}

function FormPips({
  s, n = 5, withTooltips = false, recentMatches, align = "left",
}: {
  s: string | null; n?: number; withTooltips?: boolean;
  recentMatches?: RecentMatch[] | null; align?: "left" | "right";
}) {
  const [hovered, setHovered] = useState<{ idx: number; rect: DOMRect } | null>(null);
  if (!s) return <span className="text-[#4A4744] text-[9px]">—</span>;
  const tail = s.toUpperCase().slice(-n);

  if (!withTooltips) {
    return (
      <span className="flex items-center gap-1">
        {[...tail].map((c, i) => (
          <span key={i} title={_resultLabel(c)} className={cn(
            "inline-block w-[9px] h-[9px] rounded-full",
            c === "W" ? "bg-[#22C55E]" : c === "D" ? "bg-[#4A4744]" : "bg-[#F05252]/70",
          )} />
        ))}
      </span>
    );
  }

  return (
    <>
      <span className={cn("flex items-center gap-[5px]", align === "right" && "flex-row-reverse")}>
        {[...tail].map((c, i) => (
          <span key={i} className="relative cursor-default"
            onMouseEnter={(e) => setHovered({ idx: i, rect: e.currentTarget.getBoundingClientRect() })}
            onMouseLeave={() => setHovered(null)}
          >
            <span className={cn(
              "inline-block w-[11px] h-[11px] rounded-full",
              c === "W" ? "bg-[#22C55E]" : c === "D" ? "bg-[#4A4744]" : "bg-[#F05252]/70",
            )} />
          </span>
        ))}
      </span>
      {hovered !== null && (
        <PipTooltip c={tail[hovered.idx] ?? ""} match={recentMatches?.[hovered.idx]} rect={hovered.rect} />
      )}
    </>
  );
}

function TeamLogo({ url, name, size = 28 }: { url: string | null; name: string; size?: number }) {
  const sz = `${size}px`;
  if (!url) {
    return (
      <div
        className="rounded-xl bg-[#1C1C1C] border border-[rgba(255,255,255,0.07)] flex items-center justify-center shrink-0"
        style={{ width: sz, height: sz }}
      >
        <span className="font-bold text-[#4A4744]" style={{ fontSize: Math.max(8, Math.round(size * 0.28)) }}>
          {name.slice(0, 2).toUpperCase()}
        </span>
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt={name} width={size} height={size}
      className="object-contain shrink-0" style={{ width: sz, height: sz }}
      onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden"; }} />
  );
}

function PositionBar({ position, total }: { position: number; total: number | null }) {
  const segments  = Math.min(Math.max(total ?? position, position), 32);
  const quartile  = position / segments;
  const barColor  =
    quartile <= 0.25 ? "#22C55E"
    : quartile <= 0.5  ? "#7A7673"
    : quartile <= 0.75 ? "#4A4744"
    : "#F05252";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-end gap-[2px]">
        {Array.from({ length: segments }, (_, i) => {
          const rank      = i + 1;
          const isCurrent = rank === position;
          const isAbove   = rank < position;
          return (
            <div key={i} className="rounded-[1px] shrink-0" style={{
              width: 4, height: isCurrent ? 7 : 4,
              background: isCurrent ? barColor : isAbove ? "rgba(255,255,255,0.2)" : "rgba(255,255,255,0.07)",
            }} />
          );
        })}
      </div>
      <span className="text-[8px] text-[#4A4744] tabular-nums leading-none">
        {position}.{total != null ? ` av ${total}` : ""}
      </span>
    </div>
  );
}

function GroupHeader({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2.5 px-6 pt-5 pb-1">
      <span className="text-[8.5px] font-bold text-[#F5C030] uppercase tracking-[0.22em] shrink-0 leading-none">
        {label}
      </span>
      <div className="flex-1 h-px bg-[rgba(255,255,255,0.07)]" />
    </div>
  );
}

// ── Stat row ──────────────────────────────────────────────────────────────────

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

function StatRow({ label, homeText, awayText, homeRaw, awayRaw, lowerIsBetter = false, noBar = false, signed = false }: StatRowProps) {
  const both = homeRaw != null && awayRaw != null;

  if (signed) {
    const signCls = (n: number | null) =>
      n == null ? "text-[#4A4744]" : n > 0 ? "text-[#22C55E]" : n < 0 ? "text-[#F05252]" : "text-[#7A7673]";
    return (
      <div className="py-2.5 border-b border-[rgba(255,255,255,0.06)] last:border-0">
        <div className="grid grid-cols-[1fr_100px_1fr] items-center gap-2">
          <div className="text-right">
            <span className={cn("text-[16px] font-bold tabular-nums leading-none tracking-tight", signCls(homeRaw ?? null))}>{homeText}</span>
          </div>
          <div className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-[0.14em] text-center leading-snug px-1">{label}</div>
          <div>
            <span className={cn("text-[16px] font-bold tabular-nums leading-none tracking-tight", signCls(awayRaw ?? null))}>{awayText}</span>
          </div>
        </div>
      </div>
    );
  }

  const homeWins = both ? (lowerIsBetter ? homeRaw! < awayRaw! : homeRaw! > awayRaw!) : false;
  const awayWins = both ? (lowerIsBetter ? awayRaw! < homeRaw! : awayRaw! > homeRaw!) : false;
  const hCls = homeWins ? "text-[#F5C030]" : both ? "text-[#7A7673]" : "text-[#4A4744]";
  const aCls = awayWins ? "text-[#22C55E]" : both ? "text-[#7A7673]" : "text-[#4A4744]";

  const rawH = both ? (lowerIsBetter ? awayRaw! : homeRaw!) : 0;
  const rawA = both ? (lowerIsBetter ? homeRaw! : awayRaw!) : 0;
  const rawTotal = rawH + rawA;
  const showBar = !noBar && both && rawTotal > 0;
  const hShare = showBar ? Math.max(0.08, Math.min(0.92, rawH / rawTotal)) : 0;

  return (
    <div className="py-2.5 border-b border-[rgba(255,255,255,0.06)] last:border-0">
      <div className="grid grid-cols-[1fr_100px_1fr] items-center gap-2">
        <div className="text-right">
          <span className={cn("text-[16px] font-bold tabular-nums leading-none tracking-tight", hCls)}>{homeText}</span>
        </div>
        <div className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-[0.14em] text-center leading-snug px-1">{label}</div>
        <div>
          <span className={cn("text-[16px] font-bold tabular-nums leading-none tracking-tight", aCls)}>{awayText}</span>
        </div>
      </div>
      {showBar && (
        <div className="mt-[7px] flex h-[3px] rounded-full overflow-hidden">
          <div style={{ flex: hShare, background: homeWins ? "rgba(245,192,48,0.35)" : "rgba(255,255,255,0.06)" }} />
          <div style={{ flex: 1 - hShare, background: awayWins ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.06)" }} />
        </div>
      )}
    </div>
  );
}

// ── Signals ───────────────────────────────────────────────────────────────────

interface Signal { text: string; side: "home" | "away" | "neutral"; }

function buildSignals(e: MatchEnrichment, homeTeam: string, awayTeam: string): Signal[] {
  const out: Signal[] = [];

  if (e.home_position != null && e.away_position != null && Math.abs(e.home_position - e.away_position) >= 3) {
    if (e.home_position < e.away_position)
      out.push({ text: `${homeTeam} er rangert ${e.home_position}. i ${e.league_name ?? "ligaen"}, klart over ${awayTeam} på ${e.away_position}. plass.`, side: "home" });
    else
      out.push({ text: `${awayTeam} er høyest rangert (${e.away_position}.) — ${homeTeam} følger på ${e.home_position}. plass.`, side: "away" });
  }

  const hf5 = formScore(e.home_last_5); const af5 = formScore(e.away_last_5);
  if (hf5 != null && af5 != null && Math.abs(hf5 - af5) > 12) {
    const better = hf5 > af5 ? homeTeam : awayTeam;
    const bForm  = hf5 > af5 ? e.home_last_5?.slice(-5) : e.away_last_5?.slice(-5);
    const worse  = hf5 > af5 ? awayTeam : homeTeam;
    const wForm  = hf5 > af5 ? e.away_last_5?.slice(-5) : e.home_last_5?.slice(-5);
    out.push({ text: `${better} er i bedre løpsform siste 5 (${bForm}) enn ${worse} (${wForm}).`, side: hf5 > af5 ? "home" : "away" });
  }

  const hGF = e.home_avg_goals_for; const aGF = e.away_avg_goals_for;
  if (hGF != null && aGF != null && Math.abs(hGF - aGF) > 0.35) {
    const better = hGF > aGF ? homeTeam : awayTeam;
    const worse  = hGF > aGF ? awayTeam : homeTeam;
    out.push({ text: `${better} scorer ${Math.max(hGF,aGF).toFixed(1)} mål per kamp — mer enn ${worse} (${Math.min(hGF,aGF).toFixed(1)}).`, side: hGF > aGF ? "home" : "away" });
  }

  const hGA = e.home_avg_goals_against; const aGA = e.away_avg_goals_against;
  if (hGA != null && aGA != null && Math.abs(hGA - aGA) > 0.35 && out.length < 4) {
    const better = hGA < aGA ? homeTeam : awayTeam;
    const worse  = hGA < aGA ? awayTeam : homeTeam;
    out.push({ text: `${better} slipper inn ${Math.min(hGA,aGA).toFixed(1)} mål per kamp — klart bedre forsvar enn ${worse} (${Math.max(hGA,aGA).toFixed(1)}).`, side: hGA < aGA ? "home" : "away" });
  }

  if (e.home_position != null && e.away_position != null && hf5 != null && af5 != null &&
      (e.home_position < e.away_position) !== (hf5 > af5) && Math.abs(hf5 - af5) > 18 && out.length < 4) {
    const ranked = e.home_position < e.away_position ? homeTeam : awayTeam;
    const formed = hf5 > af5 ? homeTeam : awayTeam;
    if (ranked !== formed)
      out.push({ text: `${ranked} er rangert høyest, men ${formed} er i klart bedre form — signalene peker i hver sin retning.`, side: "neutral" });
  }

  return out.slice(0, 4);
}

// ── TeamComparisonCard ────────────────────────────────────────────────────────

function TeamComparisonCard({ match, enrichment, colSpan, hasCrowdData }: {
  match: MatchResult; enrichment: MatchEnrichment | null; colSpan: number; hasCrowdData: boolean;
}) {
  const hasData     = enrichment?.has_api_football_data ?? false;
  const e           = enrichment;
  const hFS         = e?.home_recent_fixture_stats ?? null;
  const aFS         = e?.away_recent_fixture_stats ?? null;
  const hasFixStats = hFS != null || aFS != null;

  const hGF = hasData ? e!.home_goals_for    : null;
  const hGA = hasData ? e!.home_goals_against : null;
  const aGF = hasData ? e!.away_goals_for    : null;
  const aGA = hasData ? e!.away_goals_against : null;
  const hGD = hGF != null && hGA != null ? hGF - hGA : null;
  const aGD = aGF != null && aGA != null ? aGF - aGA : null;

  const hAvgGF = hasData ? e!.home_avg_goals_for     : null;
  const aAvgGF = hasData ? e!.away_avg_goals_for     : null;
  const hAvgGA = hasData ? e!.home_avg_goals_against : null;
  const aAvgGA = hasData ? e!.away_avg_goals_against : null;
  const leagueSize = hasData ? (e!.league_size ?? null) : null;
  const signals    = hasData ? buildSignals(e!, match.home_team, match.away_team) : [];

  const wdlStr = (w: number | null, d: number | null, l: number | null) =>
    w != null && d != null && l != null ? `${w}–${d}–${l}` : "—";
  const recordStr = (s: string | null) => {
    if (!s) return "—";
    const w = s.match(/W(\d+)/i); const d = s.match(/D(\d+)/i); const l = s.match(/L(\d+)/i);
    return (w && d && l) ? `${w[1]}–${d[1]}–${l[1]}` : s;
  };
  const hRec = recordScore(hasData ? e!.home_home_record : null);
  const aRec = recordScore(hasData ? e!.away_away_record : null);
  const venueGames = (s: string | null) =>
    !s ? 0 : parseInt(s.match(/W(\d+)/i)?.[1] ?? "0") + parseInt(s.match(/D(\d+)/i)?.[1] ?? "0") + parseInt(s.match(/L(\d+)/i)?.[1] ?? "0");
  const hHomeGames    = hasData ? venueGames(e!.home_home_record) : 0;
  const aAwayGames    = hasData ? venueGames(e!.away_away_record) : 0;
  const hasVenueGoals = hasData && ((e!.home_avg_goals_for_home != null && hHomeGames > 0) || (e!.away_avg_goals_for_away != null && aAwayGames > 0));
  const hasVenueConc  = hasData && ((e!.home_avg_goals_against_home != null && hHomeGames > 0) || (e!.away_avg_goals_against_away != null && aAwayGames > 0));
  const hasVenueCS    = hasData && ((e!.home_clean_sheets_home != null && hHomeGames > 0) || (e!.away_clean_sheets_away != null && aAwayGames > 0));

  return (
    <tr>
      <td colSpan={colSpan} className="p-0 border-b border-[rgba(255,255,255,0.06)]">
        <div className="bg-[#0D0D0D] border-t border-[rgba(255,255,255,0.07)]">

          {/* HEADER */}
          <div className="grid grid-cols-2 divide-x divide-[rgba(255,255,255,0.07)] pt-5 pb-4">
            <div className="px-5 flex items-start gap-3">
              <TeamLogo url={e?.home_logo_url ?? null} name={match.home_team} size={44} />
              <div className="min-w-0 flex-1 pt-0.5">
                <div className="text-[14px] font-bold leading-tight tracking-tight text-[#E8E4DD]">{match.home_team}</div>
                <div className="text-[8px] text-[#4A4744] uppercase tracking-[0.1em] mt-0.5">
                  Hjemme{e?.league_name ? ` · ${e.league_name}` : ""}
                </div>
                {hasData && e!.home_last_5 && <div className="mt-2"><FormPips s={e!.home_last_5} n={5} withTooltips recentMatches={e!.home_recent_matches} align="left" /></div>}
                {hasData && e!.home_position != null && <div className="mt-2"><PositionBar position={e!.home_position} total={leagueSize} /></div>}
              </div>
            </div>
            <div className="px-5 flex items-start justify-end gap-3">
              <div className="min-w-0 text-right flex-1 pt-0.5">
                <div className="text-[14px] font-bold leading-tight tracking-tight text-[#E8E4DD]">{match.away_team}</div>
                <div className="text-[8px] text-[#4A4744] uppercase tracking-[0.1em] mt-0.5">
                  Borte{e?.league_name ? ` · ${e.league_name}` : ""}
                </div>
                {hasData && e!.away_last_5 && <div className="mt-2 flex justify-end"><FormPips s={e!.away_last_5} n={5} withTooltips recentMatches={e!.away_recent_matches} align="right" /></div>}
                {hasData && e!.away_position != null && <div className="mt-2 flex justify-end"><PositionBar position={e!.away_position} total={leagueSize} /></div>}
              </div>
              <TeamLogo url={e?.away_logo_url ?? null} name={match.away_team} size={44} />
            </div>
          </div>

          {/* ── SANNSYNLIGHETER — always shown in expanded card ── */}
          <GroupHeader label="Sannsynligheter" />
          <div className="px-6 pb-4">
            {/* Model H/U/B bars */}
            <div className="flex flex-col gap-[5px] mb-3">
              <ProbBar label="H" value={match.prob_h} highlighted={match.recommendation === "H"} delay={0} />
              <ProbBar label="U" value={match.prob_u} highlighted={match.recommendation === "U"} delay={60} />
              <ProbBar label="B" value={match.prob_b} highlighted={match.recommendation === "B"} delay={120} />
            </div>

            {/* Crowd row */}
            {hasCrowdData && match.has_public_tips && (
              <div className="flex items-center gap-3 pt-2.5 border-t border-[rgba(255,255,255,0.05)]">
                <span className="text-[8px] font-semibold text-[#4A4744] uppercase tracking-[0.12em] w-14 shrink-0">Folket</span>
                <div className="flex items-center gap-4">
                  {(["H", "U", "B"] as const).map((label) => {
                    const v = label === "H" ? match.pub_prob_h : label === "U" ? match.pub_prob_u : match.pub_prob_b;
                    return (
                      <div key={label} className="flex items-center gap-1">
                        <span className="text-[9px] text-[#4A4744] font-semibold">{label}</span>
                        <span className={cn(
                          "text-[11px] tabular-nums font-bold",
                          label === match.recommendation ? "text-[#E8E4DD]" : "text-[#4A4744]",
                        )}>
                          {v != null ? `${Math.round(v * 100)}%` : "—"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Edge / VI / CDS strip */}
            <div className="flex items-center gap-5 pt-2.5 mt-0.5 border-t border-[rgba(255,255,255,0.05)]">
              <div className="flex items-center gap-1.5">
                <span className="text-[8px] text-[#4A4744] uppercase tracking-[0.1em] font-semibold">Edge</span>
                <EdgeBadge match={match} />
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[8px] text-[#4A4744] uppercase tracking-[0.1em] font-semibold">VI</span>
                <ViBadge vi={match.vi} />
              </div>
              {match.crowd_disagreement_score != null && (
                <div className="flex items-center gap-1.5">
                  <span className="text-[8px] text-[#4A4744] uppercase tracking-[0.1em] font-semibold">CDS</span>
                  <CdsBadge cds={match.crowd_disagreement_score} />
                </div>
              )}
            </div>
          </div>

          {hasData ? (
            <>
              {(e!.home_position != null || e!.away_position != null || e!.home_points != null || e!.home_wins != null || hGD != null) && (
                <>
                  <GroupHeader label="Tabell" />
                  <div className="px-6 pb-1">
                    {(e!.home_position != null || e!.away_position != null) && <StatRow label="Posisjon" homeText={e!.home_position != null ? `${e!.home_position}.` : "—"} awayText={e!.away_position != null ? `${e!.away_position}.` : "—"} homeRaw={e!.home_position} awayRaw={e!.away_position} lowerIsBetter />}
                    {(e!.home_points != null || e!.away_points != null) && <StatRow label="Poeng" homeText={e!.home_points != null ? String(e!.home_points) : "—"} awayText={e!.away_points != null ? String(e!.away_points) : "—"} homeRaw={e!.home_points} awayRaw={e!.away_points} />}
                    {(e!.home_wins != null || e!.away_wins != null) && <StatRow label="S – U – T" homeText={wdlStr(e!.home_wins, e!.home_draws, e!.home_losses)} awayText={wdlStr(e!.away_wins, e!.away_draws, e!.away_losses)} homeRaw={e!.home_wins} awayRaw={e!.away_wins} noBar />}
                    {(hGD != null || aGD != null) && <StatRow label="Målforskjell" homeText={hGD != null ? (hGD > 0 ? `+${hGD}` : `${hGD}`) : "—"} awayText={aGD != null ? (aGD > 0 ? `+${aGD}` : `${aGD}`) : "—"} homeRaw={hGD} awayRaw={aGD} signed />}
                  </div>
                </>
              )}

              {(hAvgGF != null || aAvgGF != null || hAvgGA != null || aAvgGA != null || e!.home_clean_sheets != null) && (
                <>
                  <GroupHeader label="Angrep / Forsvar" />
                  <div className="px-6 pb-1">
                    {(hAvgGF != null || aAvgGF != null) && <StatRow label="Mål / kamp" homeText={hAvgGF != null ? hAvgGF.toFixed(1) : "—"} awayText={aAvgGF != null ? aAvgGF.toFixed(1) : "—"} homeRaw={hAvgGF} awayRaw={aAvgGF} />}
                    {(hAvgGA != null || aAvgGA != null) && <StatRow label="Innsluppet" homeText={hAvgGA != null ? hAvgGA.toFixed(1) : "—"} awayText={aAvgGA != null ? aAvgGA.toFixed(1) : "—"} homeRaw={hAvgGA} awayRaw={aAvgGA} lowerIsBetter />}
                    {(e!.home_clean_sheets != null || e!.away_clean_sheets != null) && <StatRow label="Nullhold." homeText={e!.home_clean_sheets != null ? String(e!.home_clean_sheets) : "—"} awayText={e!.away_clean_sheets != null ? String(e!.away_clean_sheets) : "—"} homeRaw={e!.home_clean_sheets} awayRaw={e!.away_clean_sheets} />}
                  </div>
                </>
              )}

              {(e!.home_home_record || e!.away_away_record || hasVenueGoals) && (
                <>
                  <GroupHeader label="Hjemme / Borte" />
                  <div className="px-6 pb-1">
                    {(e!.home_home_record || e!.away_away_record) && <StatRow label="Rekord" homeText={recordStr(e!.home_home_record)} awayText={recordStr(e!.away_away_record)} homeRaw={hRec} awayRaw={aRec} noBar />}
                    {hasVenueGoals && <StatRow label="Mål / kamp" homeText={hHomeGames > 0 && e!.home_avg_goals_for_home != null ? e!.home_avg_goals_for_home.toFixed(1) : "—"} awayText={aAwayGames > 0 && e!.away_avg_goals_for_away != null ? e!.away_avg_goals_for_away.toFixed(1) : "—"} homeRaw={hHomeGames > 0 ? e!.home_avg_goals_for_home : null} awayRaw={aAwayGames > 0 ? e!.away_avg_goals_for_away : null} />}
                    {hasVenueConc && <StatRow label="Innsluppet" homeText={hHomeGames > 0 && e!.home_avg_goals_against_home != null ? e!.home_avg_goals_against_home.toFixed(1) : "—"} awayText={aAwayGames > 0 && e!.away_avg_goals_against_away != null ? e!.away_avg_goals_against_away.toFixed(1) : "—"} homeRaw={hHomeGames > 0 ? e!.home_avg_goals_against_home : null} awayRaw={aAwayGames > 0 ? e!.away_avg_goals_against_away : null} lowerIsBetter />}
                    {hasVenueCS && <StatRow label="Nullhold." homeText={hHomeGames > 0 && e!.home_clean_sheets_home != null ? String(e!.home_clean_sheets_home) : "—"} awayText={aAwayGames > 0 && e!.away_clean_sheets_away != null ? String(e!.away_clean_sheets_away) : "—"} homeRaw={hHomeGames > 0 ? e!.home_clean_sheets_home : null} awayRaw={aAwayGames > 0 ? e!.away_clean_sheets_away : null} />}
                  </div>
                </>
              )}
              <div className="pb-3" />
            </>
          ) : (
            <div className="px-6 py-8 text-center">
              <p className="text-[10px] text-[#4A4744] italic">Ingen statistikk tilgjengelig for dette oppgjøret</p>
            </div>
          )}

          {/* TOPPSTATISTIKK */}
          {hasFixStats && (() => {
            const fmt1  = (v: number | null) => v != null ? v.toFixed(1) : "—";
            const fmtP  = (v: number | null) => v != null ? `${v.toFixed(0)}%` : "—";
            const fmtXg = (v: number | null) => v != null ? v.toFixed(2) : "—";
            const n = Math.min(hFS?.sample_size ?? Infinity, aFS?.sample_size ?? Infinity);
            const sampleNote = n !== Infinity && n <= 2 ? `basert på ${n} kamp${n === 1 ? "" : "er"}` : null;
            const rows: Array<{ label: string; hVal: string; aVal: string; hRaw: number | null; aRaw: number | null; lowerIsBetter?: boolean }> = [];
            if (hFS?.avg_possession != null || aFS?.avg_possession != null)       rows.push({ label: "Ballbesittelse",    hVal: fmtP(hFS?.avg_possession ?? null),    aVal: fmtP(aFS?.avg_possession ?? null),    hRaw: hFS?.avg_possession ?? null,    aRaw: aFS?.avg_possession ?? null });
            if (hFS?.avg_total_shots != null || aFS?.avg_total_shots != null)     rows.push({ label: "Skudd",              hVal: fmt1(hFS?.avg_total_shots ?? null),   aVal: fmt1(aFS?.avg_total_shots ?? null),   hRaw: hFS?.avg_total_shots ?? null,   aRaw: aFS?.avg_total_shots ?? null });
            if (hFS?.avg_shots_on_goal != null || aFS?.avg_shots_on_goal != null) rows.push({ label: "Skudd på mål",       hVal: fmt1(hFS?.avg_shots_on_goal ?? null), aVal: fmt1(aFS?.avg_shots_on_goal ?? null), hRaw: hFS?.avg_shots_on_goal ?? null, aRaw: aFS?.avg_shots_on_goal ?? null });
            if (hFS?.avg_corners != null || aFS?.avg_corners != null)             rows.push({ label: "Cornere",            hVal: fmt1(hFS?.avg_corners ?? null),       aVal: fmt1(aFS?.avg_corners ?? null),       hRaw: hFS?.avg_corners ?? null,       aRaw: aFS?.avg_corners ?? null });
            if (hFS?.avg_pass_accuracy != null || aFS?.avg_pass_accuracy != null) rows.push({ label: "Pasninger %",        hVal: fmtP(hFS?.avg_pass_accuracy ?? null), aVal: fmtP(aFS?.avg_pass_accuracy ?? null), hRaw: hFS?.avg_pass_accuracy ?? null, aRaw: aFS?.avg_pass_accuracy ?? null });
            if (hFS?.avg_fouls != null || aFS?.avg_fouls != null)                 rows.push({ label: "Frispark",           hVal: fmt1(hFS?.avg_fouls ?? null),         aVal: fmt1(aFS?.avg_fouls ?? null),         hRaw: hFS?.avg_fouls ?? null,         aRaw: aFS?.avg_fouls ?? null,         lowerIsBetter: true });
            if (hFS?.avg_yellow_cards != null || aFS?.avg_yellow_cards != null)   rows.push({ label: "Gule kort",          hVal: fmt1(hFS?.avg_yellow_cards ?? null),  aVal: fmt1(aFS?.avg_yellow_cards ?? null),  hRaw: hFS?.avg_yellow_cards ?? null,  aRaw: aFS?.avg_yellow_cards ?? null,  lowerIsBetter: true });
            if (hFS?.avg_xg != null || aFS?.avg_xg != null)                       rows.push({ label: "Forventa mål (xG)", hVal: fmtXg(hFS?.avg_xg ?? null),          aVal: fmtXg(aFS?.avg_xg ?? null),          hRaw: hFS?.avg_xg ?? null,            aRaw: aFS?.avg_xg ?? null });
            if (rows.length === 0) return null;
            return (
              <>
                <GroupHeader label="Toppstatistikk" />
                <div className="px-6 pb-1">
                  {rows.map((row) => <StatRow key={row.label} label={row.label} homeText={row.hVal} awayText={row.aVal} homeRaw={row.hRaw} awayRaw={row.aRaw} lowerIsBetter={row.lowerIsBetter} />)}
                  {sampleNote && <div className="pt-2 pb-1 text-right"><span className="text-[8px] text-[#4A4744] italic">{sampleNote}</span></div>}
                </div>
                <div className="pb-2" />
              </>
            );
          })()}

          {/* ANALYSE */}
          {signals.length > 0 && (
            <>
              <GroupHeader label="Analyse" />
              <div className="px-6 pb-5 pt-2 space-y-3">
                {signals.map((sig, i) => (
                  <div key={i} className="flex gap-3 items-start">
                    <div
                      className="w-[2px] shrink-0 rounded-full self-stretch mt-[2px]"
                      style={{
                        minHeight: 14,
                        background: sig.side === "home" ? "#F5C030" : sig.side === "away" ? "#22C55E" : "rgba(255,255,255,0.15)",
                      }}
                    />
                    <p className="text-[11px] text-[#7A7673] leading-relaxed">{sig.text}</p>
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
    <tr className="border-b border-[rgba(255,255,255,0.04)]" style={{ animationDelay: `${i * 35}ms` }}>
      <td className="py-3 px-3"><div className="skeleton h-3 w-4 rounded" /></td>
      <td className="py-3 px-3">
        <div className="space-y-1.5">
          <div className="skeleton h-3 rounded" style={{ width: `${58 + (i * 19) % 28}%` }} />
          <div className="skeleton h-2.5 w-20 rounded" />
        </div>
      </td>
      {/* Pick, Edge, VI, Analyse */}
      {[32, 48, 36, 52].map((w, j) => (
        <td key={j} className="py-3 px-3">
          <div className="skeleton h-3 rounded mx-auto" style={{ width: w }} />
        </td>
      ))}
    </tr>
  );
}

// ── Match row ─────────────────────────────────────────────────────────────────

function MatchRow({
  match, enrichment, index, isExpanded, onToggle, showCrowd,
}: {
  match: MatchResult;
  enrichment: MatchEnrichment | null;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
  showCrowd: boolean;
}) {
  const isConviction = match.is_conviction;
  const picks        = sortSigns(match.picks);
  const tileSize     = picks.length === 1 ? 32 : picks.length === 2 ? 27 : 22;

  return (
    <>
      <tr
        className={cn(
          "border-b border-[rgba(255,255,255,0.05)] transition-colors duration-100 animate-fade-up group cursor-pointer",
          isExpanded ? "bg-[#1A1A1A]" : "hover:bg-[#141414]",
        )}
        style={{
          animationDelay: `${index * 38}ms`,
          borderLeft: isConviction ? "2px solid rgba(245,192,48,0.5)" : "2px solid transparent",
        }}
        onClick={onToggle}
      >
        {/* # */}
        <td className="py-4 pl-4 pr-2 w-8">
          <span className="text-[12px] text-[#4A4744] tabular-nums font-medium">{match.match_number}</span>
        </td>

        {/* Teams */}
        <td className="py-4 px-3">
          <div className="flex items-center gap-2 min-w-0">
            <SmallLogo url={enrichment?.home_logo_url} name={match.home_team} />
            <span className="text-[15px] font-semibold text-[#E8E4DD] truncate leading-none tracking-tight">
              {match.home_team}
              <span className="text-[#3A3835] font-normal mx-1.5">–</span>
              {match.away_team}
            </span>
            <SmallLogo url={enrichment?.away_logo_url} name={match.away_team} />
            {isConviction && (
              <span className="relative flex h-1.5 w-1.5 shrink-0 ml-0.5">
                <span className="absolute inset-0 rounded-full bg-[#F5C030] animate-ping opacity-40" />
                <span className="relative rounded-full h-1.5 w-1.5 bg-[#F5C030]" />
              </span>
            )}
          </div>
        </td>

        {/* Pick tiles */}
        <td className="py-4 px-3">
          <div className="flex items-center gap-1">
            {picks.map((p) => (
              <PickTile
                key={p}
                pick={p}
                isPrimary={p === match.recommendation}
                isConviction={isConviction}
                size={tileSize}
              />
            ))}
          </div>
        </td>

        <td className="py-4 px-3 text-right w-20"><EdgeBadge match={match} /></td>
        <td className="py-4 px-3 text-center w-16"><ViBadge vi={match.vi} /></td>

        <td className="py-4 pr-4 pl-1 w-20">
          <span className={cn(
            "inline-flex items-center gap-1 text-[10px] transition-colors select-none font-medium",
            isExpanded ? "text-[#E8E4DD]" : "text-[#4A4744] group-hover:text-[#7A7673]",
          )}>
            <span>{isExpanded ? "▴" : "▾"}</span>
            <span className="hidden sm:inline">{isExpanded ? "Lukk" : "Analyse"}</span>
          </span>
        </td>
      </tr>

      {isExpanded && (
        <TeamComparisonCard match={match} enrichment={enrichment} colSpan={6} hasCrowdData={showCrowd} />
      )}
    </>
  );
}

// ── Table group header row ────────────────────────────────────────────────────

function TableGroupDivider({ label, count, note }: { label: string; count: number; note?: string }) {
  return (
    <tr>
      <td colSpan={6} style={{ padding: "20px 16px 6px", borderBottom: "none" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span
            style={{
              fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700,
              color: "var(--gold)", letterSpacing: "0.20em",
              textTransform: "uppercase", lineHeight: 1, flexShrink: 0,
            }}
          >
            {label}
          </span>
          {note && (
            <span
              style={{
                fontFamily: "var(--font-mono)", fontSize: 9,
                color: "rgba(255,255,255,0.14)", letterSpacing: "0.08em",
              }}
            >
              · {note}
            </span>
          )}
          <span
            style={{
              fontFamily: "var(--font-mono)", fontSize: 9,
              color: "#3A3835", fontVariantNumeric: "tabular-nums",
            }}
          >
            {count} kamp{count !== 1 ? "er" : ""}
          </span>
          <div style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.05)" }} />
        </div>
      </td>
    </tr>
  );
}

// ── Table ─────────────────────────────────────────────────────────────────────

interface MatchTableProps {
  matches: MatchResult[];
  enrichmentMap?: Map<number, MatchEnrichment>;
  isLoading?: boolean;
  footer?: React.ReactNode;
  grouped?: boolean;
}

const TH = "text-[9px] font-semibold text-[#4A4744] uppercase tracking-[1.2px] py-2.5 px-3 whitespace-nowrap bg-[#141414]";

export function MatchTable({ matches, enrichmentMap, isLoading, footer, grouped }: MatchTableProps) {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const hasCrowdData = !isLoading && matches.some((m) => m.has_public_tips);

  // Build ordered list with group divider markers when grouped=true
  type GroupedItem =
    | { type: "divider"; label: string; count: number; note?: string }
    | { type: "match"; match: MatchResult; index: number };

  const items: GroupedItem[] = (() => {
    if (!grouped || isLoading) return [];

    // Sort by picks.length ascending; within singles, conviction picks first
    const singles  = matches
      .filter(m => m.picks.length === 1)
      .sort((a, b) => (b.is_conviction ? 1 : 0) - (a.is_conviction ? 1 : 0));
    const halvdekk = matches.filter(m => m.picks.length === 2);
    const heldekk  = matches.filter(m => m.picks.length >= 3);

    const result: GroupedItem[] = [];
    let runningIndex = 0;

    const addGroup = (label: string, group: MatchResult[], note?: string) => {
      if (group.length === 0) return;
      result.push({ type: "divider", label, count: group.length, note });
      for (const m of group) {
        result.push({ type: "match", match: m, index: runningIndex++ });
      }
    };

    addGroup("Singel", singles, "1 tegn");
    addGroup("Halvdekk", halvdekk, "2 tegn");
    addGroup("Heldekk", heldekk, "3 tegn");

    return result;
  })();

  return (
    <div className="rounded-xl border border-[rgba(255,255,255,0.07)] bg-[#141414] overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-[rgba(255,255,255,0.07)]">
              <th className={cn(TH, "pl-4 pr-2 text-left w-8")}>#</th>
              <th className={cn(TH, "text-left")}>Kamp</th>
              <th className={cn(TH, "text-left")}>Pick</th>
              <th className={cn(TH, "text-right w-20")}>Edge</th>
              <th className={cn(TH, "text-center w-16")}>VI</th>
              <th className={cn(TH, "text-left w-20 pr-4")}></th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 12 }, (_, i) => <SkeletonRow key={i} i={i} />)
            ) : grouped ? (
              items.map((item, i) =>
                item.type === "divider" ? (
                  <TableGroupDivider key={`div-${i}`} label={item.label} count={item.count} note={item.note} />
                ) : (
                  <MatchRow
                    key={item.match.match_number}
                    match={item.match}
                    enrichment={enrichmentMap?.get(item.match.match_number) ?? null}
                    index={item.index}
                    isExpanded={expandedRow === item.match.match_number}
                    onToggle={() => setExpandedRow((p) => (p === item.match.match_number ? null : item.match.match_number))}
                    showCrowd={hasCrowdData}
                  />
                )
              )
            ) : (
              matches.map((m, i) => (
                <MatchRow
                  key={m.match_number}
                  match={m}
                  enrichment={enrichmentMap?.get(m.match_number) ?? null}
                  index={i}
                  isExpanded={expandedRow === m.match_number}
                  onToggle={() => setExpandedRow((p) => (p === m.match_number ? null : m.match_number))}
                  showCrowd={hasCrowdData}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {!isLoading && matches.length === 0 && (
        <div className="py-16 text-center text-[#4A4744] text-sm">
          Ingen kamper tilgjengelig
        </div>
      )}

      {footer}
    </div>
  );
}
