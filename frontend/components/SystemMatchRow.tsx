"use client";

import { cn } from "@/lib/utils";
import type { MatchEnrichment, MatchResult } from "@/lib/types";

export type Sign = "H" | "U" | "B";

interface SystemMatchRowProps {
  match: MatchResult;
  enrichment?: MatchEnrichment;
  signs: Set<Sign>;
  onToggle: (sign: Sign) => void;
  kickoffUtc?: string | null;
  debugMode?: boolean;
  coverageType?: "key" | "reserve" | "single";
}

// ── Data accessors ─────────────────────────────────────────────────────────────

function signValue(m: MatchResult, s: Sign): number | null {
  return s === "H" ? m.value_h : s === "U" ? m.value_u : m.value_b;
}
function signOdds(m: MatchResult, s: Sign): number {
  return s === "H" ? m.odds_h : s === "U" ? m.odds_u : m.odds_b;
}
function signNt(m: MatchResult, s: Sign): number | null {
  return s === "H" ? m.pub_prob_h : s === "U" ? m.pub_prob_u : m.pub_prob_b;
}
function signBmProb(m: MatchResult, s: Sign): number {
  return s === "H" ? m.bm_prob_h : s === "U" ? m.bm_prob_u : m.bm_prob_b;
}
function signModelProb(m: MatchResult, s: Sign): number {
  return s === "H" ? m.prob_h : s === "U" ? m.prob_u : m.prob_b;
}

// ── Value Index ────────────────────────────────────────────────────────────────

function computeVI(bmProb: number, nt: number | null): number | null {
  if (nt == null || nt < 0.02) return null;
  return Math.min(5.0, bmProb / nt);
}

// ── VI text colour — applied ONLY to the number, nothing else ─────────────────

function viColor(vi: number | null): { color: string; weight: number } {
  if (vi == null)   return { color: "#D5D0C8", weight: 500 };
  if (vi >= 1.50)   return { color: "#14532D", weight: 800 };
  if (vi >= 1.20)   return { color: "#15803D", weight: 700 };
  if (vi >= 1.00)   return { color: "#16A34A", weight: 600 };
  if (vi >= 0.90)   return { color: "#ADA9A2", weight: 500 };
  if (vi >= 0.70)   return { color: "#92400E", weight: 600 };
  return               { color: "#991B1B", weight: 700 };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatKickoff(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const date = new Date(iso);
    const day  = date.toLocaleDateString("nb-NO", { weekday: "long" });
    const time = date.toLocaleTimeString("nb-NO", { hour: "2-digit", minute: "2-digit" });
    return `${day.charAt(0).toUpperCase() + day.slice(1)} • ${time}`;
  } catch {
    return null;
  }
}

function TeamLogo({ url, name }: { url: string | null | undefined; name: string }) {
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

// ── Sign tile column ───────────────────────────────────────────────────────────
//
// Identical compact style to MatchTable's PickTile column.
// Structure (top → bottom):
//   [tile]      ← 28 px square, dark when selected, neutral when not
//   4.83        ← odds, 9 px muted
//   21%         ← NT public %, 9 px
//   1.87        ← Value Index, 11 px, COLOUR ONLY on this number
//

function SignTile({
  sign, selected, value, odds, nt, bmProb, modelProb, onToggle, debugMode,
}: {
  sign: Sign;
  selected: boolean;
  value: number | null;
  odds: number;
  nt: number | null;
  bmProb: number;
  modelProb: number;
  onToggle: () => void;
  debugMode: boolean;
}) {
  const vi       = computeVI(bmProb, nt);
  const modelVI  = computeVI(modelProb, nt);
  const vc       = viColor(vi);

  // PickTile colours: matches MatchTable exactly
  const tileBg     = selected ? "#111110" : "#F5F3EF";
  const tileBorder = selected ? "none"    : "1.5px solid #D5D0C8";
  const tileColor  = selected ? "#FFFFFF" : "#ADA9A2";

  return (
    <div className="flex flex-col items-center" style={{ width: 52 }}>

      {/* Clickable tile — same style as MatchTable PickTile */}
      <div
        role="button"
        aria-pressed={selected}
        aria-label={`${selected ? "Fjern" : "Velg"} ${sign}`}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === " " || e.key === "Enter") { e.preventDefault(); onToggle(); }
        }}
        tabIndex={0}
        className="select-none active:scale-[0.90] focus:outline-none focus-visible:ring-2 focus-visible:ring-[#D4930A]/40 transition-colors duration-100"
        style={{
          width: 28, height: 28,
          borderRadius: 4,
          background: tileBg,
          border: tileBorder,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, cursor: "pointer", outline: "none",
        }}
      >
        <span style={{
          fontSize: 12, fontWeight: 700, color: tileColor,
          letterSpacing: "0.04em", lineHeight: 1,
        }}>
          {sign}
        </span>
      </div>

      {/* Odds — most muted */}
      <span style={{
        fontSize: 9, color: "#C8C4BC", lineHeight: 1,
        marginTop: 5, fontVariantNumeric: "tabular-nums",
      }}>
        {odds > 0 ? odds.toFixed(2) : "—"}
      </span>

      {/* NT public % */}
      <span style={{
        fontSize: 9, fontWeight: 500, color: "#6B6862", lineHeight: 1,
        marginTop: 2, fontVariantNumeric: "tabular-nums",
      }}>
        {nt != null ? `${Math.round(nt * 100)}%` : "—"}
      </span>

      {/* Value Index — the ONLY coloured element */}
      <span
        style={{
          fontSize: 11,
          fontWeight: vc.weight,
          color: vc.color,
          lineHeight: 1,
          marginTop: 3,
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "-0.01em",
        }}
        title="Market Value Index = Oddsimplisert% ÷ Folket%"
      >
        {vi != null ? vi.toFixed(2) : "—"}
      </span>

      {/* Debug panel */}
      {debugMode && (
        <div style={{
          marginTop: 5,
          paddingTop: 4,
          borderTop: "1px solid #E4E1DA",
          width: "100%",
          fontSize: 7,
          lineHeight: 1.7,
          color: "#ADA9A2",
          fontVariantNumeric: "tabular-nums",
          textAlign: "center",
        }}>
          <div>Bm {(bmProb * 100).toFixed(1)}%</div>
          <div>M  {(modelProb * 100).toFixed(1)}%</div>
          <div>O  {odds > 0 ? (100 / odds).toFixed(1) : "—"}%</div>
          <div style={{ color: vc.color, fontWeight: 700 }}>VI {vi?.toFixed(2) ?? "—"}</div>
          <div>VI-E {modelVI?.toFixed(2) ?? "—"}</div>
          <div>E  {value != null ? `${value > 0 ? "+" : ""}${value.toFixed(1)}pp` : "—"}</div>
        </div>
      )}
    </div>
  );
}

// ── Row ───────────────────────────────────────────────────────────────────────

export function SystemMatchRow({
  match, enrichment, signs, onToggle, kickoffUtc, debugMode = false, coverageType,
}: SystemMatchRowProps) {
  const inSystem = signs.size > 0;
  const kickoff  = formatKickoff(kickoffUtc);

  const matchNumColor =
    coverageType === "key"     ? "#D4930A" :
    coverageType === "reserve" ? "#ADA9A2" :
    "#C8C4BC";

  return (
    <div className={cn(
      "flex items-center gap-3 px-4 border-b border-[#F0EDE8]",
      "transition-colors duration-100 hover:bg-[#FAFAF8]",
      !inSystem && "opacity-30",
    )} style={{ paddingTop: 10, paddingBottom: 10 }}>

      {/* Match number — amber for key, slate for reserve, default otherwise */}
      <span
        className="text-[11px] tabular-nums font-medium w-5 shrink-0 text-right select-none"
        style={{ color: matchNumColor }}
      >
        {match.match_number}
      </span>

      {/* Teams + kickoff */}
      <div className="flex flex-col justify-center flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <TeamLogo url={enrichment?.home_logo_url} name={match.home_team} />
          <span className="text-[13px] font-semibold text-[#111110] truncate leading-none">
            {match.home_team}
            <span className="text-[#C8C4BC] font-normal mx-1.5">–</span>
            {match.away_team}
          </span>
          <TeamLogo url={enrichment?.away_logo_url} name={match.away_team} />
        </div>
        {kickoff && (
          <span className="text-[10px] text-[#ADA9A2] leading-tight mt-1">
            {kickoff}
          </span>
        )}
      </div>

      {/* Sign tiles */}
      <div className="flex gap-2 shrink-0">
        {(["H", "U", "B"] as Sign[]).map((sign) => (
          <SignTile
            key={sign}
            sign={sign}
            selected={signs.has(sign)}
            value={signValue(match, sign)}
            odds={signOdds(match, sign)}
            nt={signNt(match, sign)}
            bmProb={signBmProb(match, sign)}
            modelProb={signModelProb(match, sign)}
            onToggle={() => onToggle(sign)}
            debugMode={debugMode}
          />
        ))}
      </div>
    </div>
  );
}
