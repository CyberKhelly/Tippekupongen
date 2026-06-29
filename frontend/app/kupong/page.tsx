"use client";

import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import Link from "next/link";
import { getCoupons, optimize, getSyncStatus, getEnrichment } from "@/lib/api";
import type { MatchResult, MatchEnrichment, OptimizeResponse, Strategy } from "@/lib/types";
import type { CouponListItem } from "@/lib/types";
import { CouponSelector } from "@/components/CouponSelector";
import { secsUntil, recValue, sortSigns } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

// ── Polling helpers ───────────────────────────────────────────────────────────

function syncInterval(isRunning: boolean, secs: number): number {
  if (isRunning) return 5_000;
  if (secs < 30 * 60) return 30_000;
  if (secs < 3 * 60 * 60) return 60_000;
  return 120_000;
}
function optimizeInterval(secs: number): number {
  if (secs < 30 * 60) return 60_000;
  if (secs < 3 * 60 * 60) return 3 * 60_000;
  return 5 * 60_000;
}

// ── Slider → strategy ─────────────────────────────────────────────────────────

function sliderToStrategy(pos: number): Strategy {
  if (pos <= 33) return "safe";
  if (pos <= 66) return "balanced";
  return "jackpot";
}

function strategyToSlider(s: Strategy): number {
  if (s === "safe") return 16;
  if (s === "balanced") return 50;
  return 84;
}

const SLIDER_LABEL: Record<number, string> = {};
function sliderDescription(pos: number): { label: string; body: string } {
  if (pos <= 20) return {
    label: "Treffsikkerhet",
    body: "Prioriterer riktige tegn. Singel på de sikreste, minimal dekning på resten.",
  };
  if (pos <= 40) return {
    label: "Forsiktig balansert",
    body: "Mer vekt på å treffe riktig enn å maksimere jackpotpotensial.",
  };
  if (pos <= 60) return {
    label: "Balansert",
    body: "Optimal balanse mellom sikre singel-valg og dekning mot usikre kamper.",
  };
  if (pos <= 80) return {
    label: "Jackpot-orientert",
    body: "Økt dekning og flere rader. Høyere jackpotpotensial, mer varians.",
  };
  return {
    label: "Jackpotpotensial",
    body: "Maksimal dekning på usikre kamper. Høy oppside, høy varians.",
  };
}

// ── Data helpers ──────────────────────────────────────────────────────────────

function modelPct(m: MatchResult): number {
  const v = m.recommendation === "H" ? m.prob_h : m.recommendation === "U" ? m.prob_u : m.prob_b;
  return Math.round(v * 100);
}

function pubPct(m: MatchResult): number | null {
  if (!m.has_public_tips) return null;
  const v = m.recommendation === "H" ? m.pub_prob_h : m.recommendation === "U" ? m.pub_prob_u : m.pub_prob_b;
  return v !== null ? Math.round(v * 100) : null;
}

function edgePp(m: MatchResult): number | null {
  if (!m.has_public_tips) return null;
  return recValue(m.recommendation, m.value_h, m.value_u, m.value_b);
}

function pickLabel(pick: string): string {
  return ({ H: "Hjemme", U: "Uavgjort", B: "Borte" }[pick] ?? pick);
}

function coverageColor(type: string): string {
  if (type === "single")     return "var(--green)";
  if (type === "half_cover") return "var(--gold)";
  return "var(--tx-3)";
}

// ── Narrative ─────────────────────────────────────────────────────────────────

function shortNarrative(m: MatchResult): string {
  const edge    = edgePp(m);
  const pub     = pubPct(m);
  const model   = modelPct(m);
  const pick    = m.recommendation;
  const name    = pick === "H" ? m.home_team : pick === "B" ? m.away_team : "Uavgjort";

  if (edge === null || pub === null) return `Modellen har ${model >= 68 ? "sterk" : "god"} tro på ${name}.`;
  if (edge >= 10) return `${name} undervurdert av spillerne — ${pub}% vs modellens ${model}%.`;
  if (edge >= 4)  return `Modellen ser mer verdi på ${name} enn folkemengden (${pub}% vs ${model}%).`;
  if (edge > -4)  return `Modellen og spillerne er relativt enige om ${name} (${pub}% vs ${model}%).`;
  if (edge > -10) return `${name} er populær — men modellen er mer avventende (${pub}% vs ${model}%).`;
  return `${pub}% velger ${name}, men modellen er skeptisk (${model}%).`;
}

// ── Team logo ─────────────────────────────────────────────────────────────────

function TeamLogo({ name, url, size = 32 }: { name: string; url?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const initials = name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  const hue = Array.from(name).reduce((h, c) => (h * 31 + c.charCodeAt(0)) & 0xFFFF, 0) % 360;
  const fallback = !url || failed;

  return (
    <div style={{
      width: size, height: size, borderRadius: 5,
      background: fallback ? `hsl(${hue}, 28%, 18%)` : "transparent",
      overflow: "hidden", display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      {!fallback ? (
        <img src={url!} alt={name} width={size} height={size}
             style={{ objectFit: "contain", padding: size * 0.12 }}
             onError={() => setFailed(true)} />
      ) : (
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: size * 0.28, fontWeight: 700,
          color: `hsl(${hue}, 55%, 68%)`,
        }}>{initials}</span>
      )}
    </div>
  );
}

// ── Pick chip ─────────────────────────────────────────────────────────────────

function PickChip({ sign, primary }: { sign: string; primary: boolean }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 24, height: 24, borderRadius: 7,
      background: primary ? "rgba(201,160,74,0.14)" : "rgba(255,255,255,0.06)",
      border: `1px solid ${primary ? "rgba(201,160,74,0.30)" : "rgba(255,255,255,0.09)"}`,
      fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
      color: primary ? "var(--gold)" : "var(--tx-2)", flexShrink: 0,
    }}>{sign}</span>
  );
}

// ── Compact comparison bar ────────────────────────────────────────────────────

function MiniBar({ modelV, crowdV, isPos }: { modelV: number; crowdV: number; isPos: boolean }) {
  const h = 5;
  const min = Math.min(modelV, crowdV);
  const diff = Math.abs(modelV - crowdV);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", width: 42, flexShrink: 0, letterSpacing: "0.06em" }}>
        FOLKET {crowdV}%
      </span>
      <div style={{ flex: 1, height: h, borderRadius: h / 2, background: "rgba(255,255,255,0.06)", position: "relative", overflow: "hidden" }}>
        <div style={{
          position: "absolute", left: 0, top: 0, bottom: 0,
          width: `${min}%`,
          background: "rgba(255,255,255,0.18)", borderRadius: `${h / 2}px 0 0 ${h / 2}px`,
        }} />
        {diff > 0 && (
          <div style={{
            position: "absolute",
            left: `${isPos ? crowdV : modelV}%`, top: 0, bottom: 0,
            width: `${diff}%`,
            background: isPos ? "var(--gold)" : "rgba(123,146,255,0.45)",
            borderRadius: isPos ? `0 ${h / 2}px ${h / 2}px 0` : `0 ${h / 2}px ${h / 2}px 0`,
          }} />
        )}
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-2)", width: 42, textAlign: "right", flexShrink: 0, letterSpacing: "0.06em" }}>
        MODELL {modelV}%
      </span>
    </div>
  );
}

// ── Match card ────────────────────────────────────────────────────────────────

function MatchCard({ match, enrichment, delay = 0 }: {
  match: MatchResult; enrichment: MatchEnrichment | null; delay?: number;
}) {
  const edge    = edgePp(match);
  const mPct    = modelPct(match);
  const crowd   = pubPct(match);
  const isPos   = (edge ?? 0) >= 0;
  const hasCrowd = match.has_public_tips && crowd !== null;
  const edgeColor = !hasCrowd ? "var(--tx-3)" : isPos ? "var(--gold)" : "var(--indigo)";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: EASE }}
      style={{
        padding: "16px 18px",
        background: "var(--surf-2)",
        border: "1px solid rgba(255,255,255,0.06)",
        borderRadius: 12,
      }}
    >
      {/* Team row */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <TeamLogo name={match.home_team} url={enrichment?.home_logo_url} size={28} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: "var(--font-heading)", fontSize: 13, fontWeight: 700,
            color: "var(--tx-1)", letterSpacing: "-0.015em",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {match.home_team} – {match.away_team}
          </div>
        </div>
        <TeamLogo name={match.away_team} url={enrichment?.away_logo_url} size={28} />
      </div>

      {/* Bottom row: picks + edge */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: hasCrowd ? 10 : 0 }}>
        {/* Pick chips in H→U→B order */}
        <div style={{ display: "flex", gap: 4 }}>
          {sortSigns(match.picks).map(s => (
            <PickChip key={s} sign={s} primary={s === match.recommendation} />
          ))}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--tx-3)",
            lineHeight: 1.45, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {shortNarrative(match)}
          </div>
        </div>

        {/* Edge number */}
        <div style={{
          fontFamily: "var(--font-mono)", fontWeight: 800,
          fontSize: 16, letterSpacing: "-0.03em",
          fontVariantNumeric: "tabular-nums",
          color: edgeColor, flexShrink: 0,
        }}>
          {hasCrowd && edge !== null
            ? (edge === 0 ? "JEVNT" : `${edge > 0 ? "+" : ""}${Math.abs(edge).toFixed(1)}pp`)
            : `${mPct}%`}
        </div>
      </div>

      {/* Comparison bar */}
      {hasCrowd && crowd !== null && (
        <MiniBar modelV={mPct} crowdV={crowd} isPos={isPos} />
      )}
    </motion.div>
  );
}

// ── Group section ─────────────────────────────────────────────────────────────

const GROUP_META: Record<string, { label: string; desc: string; icon: string; color: string }> = {
  single:     { label: "SINGEL",   desc: "Modellens sterkeste overbevisninger — én tegn, full premiepott", icon: "◉", color: "var(--green)" },
  half_cover: { label: "HALVDEKK", desc: "Usikre kamper med dekning — to tegn sikrer mot én feil",        icon: "◑", color: "var(--gold)" },
  full_cover: { label: "HELDEKK",  desc: "Høy usikkerhet — alle tre utfall dekkes her",                   icon: "●", color: "var(--tx-3)" },
};

function GroupSection({ slug, matches, enrichmentMap, baseDelay }: {
  slug: string; matches: MatchResult[]; enrichmentMap: Map<number, MatchEnrichment>; baseDelay: number;
}) {
  if (!matches.length) return null;
  const meta = GROUP_META[slug] ?? { label: slug.toUpperCase(), desc: "", icon: "·", color: "var(--tx-2)" };
  const hasEdge = matches.filter(m => (edgePp(m) ?? 0) >= 6).length;

  return (
    <div style={{ marginBottom: 28 }}>
      {/* Section header */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
          <span style={{ fontSize: 14, color: meta.color, lineHeight: 1 }}>{meta.icon}</span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700,
            letterSpacing: "0.14em", color: meta.color,
          }}>{meta.label}</span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)",
            background: "rgba(255,255,255,0.05)", borderRadius: 4,
            padding: "1px 6px",
          }}>
            {matches.length} kamp{matches.length !== 1 ? "er" : ""}
          </span>
          {hasEdge > 0 && slug !== "full_cover" && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--gold)", opacity: 0.8 }}>
              {hasEdge}× sterk verdi
            </span>
          )}
        </div>
        <div style={{
          fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-4)", lineHeight: 1.4,
        }}>
          {meta.desc}
        </div>
      </div>

      {/* Match cards */}
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {matches.map((m, i) => (
          <MatchCard
            key={m.match_number}
            match={m}
            enrichment={enrichmentMap.get(m.match_number) ?? null}
            delay={baseDelay + i * 0.04}
          />
        ))}
      </div>
    </div>
  );
}

// ── Config panel ──────────────────────────────────────────────────────────────

function ConfigPanel({ budget, onBudget, sliderPos, onSlider }: {
  budget: number; onBudget: (n: number) => void;
  sliderPos: number; onSlider: (n: number) => void;
}) {
  const [raw, setRaw] = useState(String(budget));
  const desc = sliderDescription(sliderPos);

  function handleBudgetBlur() {
    const n = parseInt(raw, 10);
    if (!isNaN(n) && n >= 1) { onBudget(n); setRaw(String(n)); }
    else setRaw(String(budget));
  }

  const sliderPct = `${sliderPos}%`;

  return (
    <div style={{
      background: "var(--surf-1)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 16, padding: "22px 24px 24px",
      marginBottom: 28,
    }}>
      {/* Budget row */}
      <div style={{ display: "flex", alignItems: "flex-end", gap: 20, marginBottom: 24 }}>
        <div style={{ flex: 1 }}>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
            letterSpacing: "0.14em", color: "var(--tx-4)", marginBottom: 8,
          }}>BUDSJETT</div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <input
              type="text"
              inputMode="numeric"
              value={raw}
              onChange={e => setRaw(e.target.value)}
              onBlur={handleBudgetBlur}
              onKeyDown={e => e.key === "Enter" && handleBudgetBlur()}
              className="tq-budget"
              style={{ width: 110 }}
            />
            <span style={{ fontFamily: "var(--font-sans)", fontSize: 15, color: "var(--tx-3)" }}>kr</span>
          </div>
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            {[32, 96, 192, 384].map(n => (
              <button key={n} onClick={() => { onBudget(n); setRaw(String(n)); }} style={{
                fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: budget === n ? 700 : 400,
                padding: "3px 9px", borderRadius: 6,
                background: budget === n ? "rgba(201,160,74,0.12)" : "rgba(255,255,255,0.04)",
                border: `1px solid ${budget === n ? "rgba(201,160,74,0.28)" : "rgba(255,255,255,0.08)"}`,
                color: budget === n ? "var(--gold)" : "var(--tx-3)",
                cursor: "pointer", transition: "all 0.12s",
                fontVariantNumeric: "tabular-nums",
              }}>{n}</button>
            ))}
          </div>
        </div>

        <div style={{ textAlign: "right", flexShrink: 0 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.10em", marginBottom: 4 }}>
            MAKS RADER
          </div>
          <div style={{
            fontFamily: "var(--font-mono)", fontSize: 28, fontWeight: 800,
            color: "var(--tx-1)", letterSpacing: "-0.04em", lineHeight: 1,
            fontVariantNumeric: "tabular-nums",
          }}>
            {budget}
          </div>
        </div>
      </div>

      {/* Slider */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", letterSpacing: "0.10em" }}>
            TREFFSIKKERHET
          </span>
          <span style={{
            fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: 700,
            color: "var(--gold)", letterSpacing: "-0.01em",
          }}>
            {desc.label}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", letterSpacing: "0.10em" }}>
            JACKPOTPOTENSIAL
          </span>
        </div>

        <input
          type="range"
          min={0} max={100} step={1}
          value={sliderPos}
          onChange={e => onSlider(Number(e.target.value))}
          className="tq-slider"
        />

        <div style={{
          marginTop: 10, fontFamily: "var(--font-sans)", fontSize: 12,
          color: "var(--tx-3)", lineHeight: 1.5,
        }}>
          {desc.body}
        </div>
      </div>
    </div>
  );
}

// ── Ticket card ───────────────────────────────────────────────────────────────

const RISK_LABEL: Record<Strategy, string> = {
  safe:     "Lav",
  balanced: "Middels",
  jackpot:  "Høy",
};

function TicketRow({ label, value, highlight = false, large = false }: {
  label: string; value: string; highlight?: boolean; large?: boolean;
}) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.08em",
        color: "var(--tx-4)",
      }}>{label}</span>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: large ? 15 : 12, fontWeight: large ? 800 : 600,
        color: highlight ? "var(--gold)" : "var(--tx-1)",
        fontVariantNumeric: "tabular-nums",
      }}>{value}</span>
    </div>
  );
}

function TicketDivider() {
  return (
    <div style={{
      margin: "14px -4px",
      borderTop: "1.5px dashed rgba(255,255,255,0.10)",
      position: "relative",
    }}>
      <div style={{
        position: "absolute", left: -12, top: -7,
        width: 13, height: 13, borderRadius: "50%",
        background: "var(--canvas)", border: "1.5px dashed rgba(255,255,255,0.10)",
      }} />
      <div style={{
        position: "absolute", right: -12, top: -7,
        width: 13, height: 13, borderRadius: "50%",
        background: "var(--canvas)", border: "1.5px dashed rgba(255,255,255,0.10)",
      }} />
    </div>
  );
}

function TicketCard({ result, strategy, budget, isLoading }: {
  result: OptimizeResponse | undefined; strategy: Strategy; budget: number; isLoading: boolean;
}) {
  const singles  = result?.matches.filter(m => m.coverage_type === "single").length     ?? 0;
  const halvdekk = result?.matches.filter(m => m.coverage_type === "half_cover").length ?? 0;
  const heldekk  = result?.matches.filter(m => m.coverage_type === "full_cover").length ?? 0;

  const avgEdge = useMemo(() => {
    if (!result) return null;
    const edges = result.matches.map(m => edgePp(m)).filter((e): e is number => e !== null);
    if (!edges.length) return null;
    return edges.reduce((a, b) => a + b, 0) / edges.length;
  }, [result]);

  const pWin    = result ? (result.p_win * 100) : null;
  const pvr     = result?.pvr;
  const pvrColor = !pvr ? "var(--tx-2)" : pvr >= 1.2 ? "#DCB35F" : pvr >= 1.0 ? "var(--gold)" : "var(--tx-2)";

  return (
    <div style={{
      position: "sticky", top: 60,
      background: "var(--surf-1)",
      border: "1px solid rgba(255,255,255,0.09)",
      borderRadius: 16, overflow: "visible",
      padding: "0 4px",
    }}>
      {/* Ticket header */}
      <div style={{ padding: "20px 20px 0" }}>
        <div style={{
          display: "flex", alignItems: "center", gap: 8, marginBottom: 16,
        }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8,
            background: "linear-gradient(140deg, #e4bd6a, #a87f31)",
            flexShrink: 0,
          }} />
          <div>
            <div style={{
              fontFamily: "var(--font-heading)", fontSize: 13, fontWeight: 800,
              color: "var(--tx-1)", letterSpacing: "-0.02em", lineHeight: 1.1,
            }}>TippeIQ Kupong</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
              NORSK TIPPING
            </div>
          </div>
        </div>

        <TicketRow label="BUDSJETT" value={`${budget} kr`} />
        <TicketRow label="STRATEGI" value={RISK_LABEL[strategy] + " risiko"} />
      </div>

      <TicketDivider />

      {/* Structure */}
      <div style={{ padding: "0 20px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
          DEKNINGSSTRUKTUR
        </div>

        {isLoading ? (
          <div className="animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 12, background: "rgba(255,255,255,0.06)", borderRadius: 4, marginBottom: 8 }} />
            ))}
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--green)", lineHeight: 1 }}>◉</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)", letterSpacing: "0.08em" }}>SINGEL</span>
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--tx-1)" }}>
                {singles} kamp{singles !== 1 ? "er" : ""}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--gold)", lineHeight: 1 }}>◑</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)", letterSpacing: "0.08em" }}>HALVDEKK</span>
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--tx-1)" }}>
                {halvdekk} kamp{halvdekk !== 1 ? "er" : ""}
              </span>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 2 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 11, color: "var(--tx-3)", lineHeight: 1 }}>●</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)", letterSpacing: "0.08em" }}>HELDEKK</span>
              </span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--tx-1)" }}>
                {heldekk} kamp{heldekk !== 1 ? "er" : ""}
              </span>
            </div>
          </>
        )}
      </div>

      <TicketDivider />

      {/* Stats */}
      <div style={{ padding: "0 20px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
          STATISTIKK
        </div>

        {isLoading ? (
          <div className="animate-pulse">
            {[1, 2, 3, 4].map(i => (
              <div key={i} style={{ height: 12, background: "rgba(255,255,255,0.06)", borderRadius: 4, marginBottom: 8 }} />
            ))}
          </div>
        ) : (
          <>
            <TicketRow label="RADER" value={result ? `${result.total_rows}` : "—"} />
            <TicketRow label="KOSTNAD" value={result ? `${result.total_cost} kr` : "—"} />
          </>
        )}
      </div>

      <TicketDivider />

      {/* Probability */}
      <div style={{ padding: "0 20px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
          VINNERSJANSE
        </div>

        {isLoading ? (
          <div className="animate-pulse">
            {[1, 2, 3].map(i => (
              <div key={i} style={{ height: 12, background: "rgba(255,255,255,0.06)", borderRadius: 4, marginBottom: 8 }} />
            ))}
          </div>
        ) : (
          <>
            <TicketRow
              label="P(12 RETTE)"
              value={pWin !== null ? `${pWin.toFixed(pWin < 0.1 ? 3 : 2)}%` : "—"}
              highlight
            />
            <TicketRow
              label="P(11+ RETTE)"
              value={result?.payout?.p_11 != null
                ? `${(result.payout.p_11 * 100).toFixed(1)}%`
                : "—"}
            />
            <TicketRow
              label="P(10+ RETTE)"
              value={result?.payout?.p_10 != null
                ? `${(result.payout.p_10 * 100).toFixed(1)}%`
                : "—"}
            />
          </>
        )}
      </div>

      <TicketDivider />

      {/* Value metrics */}
      <div style={{ padding: "0 20px" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
          VERDI-INDIKATORER
        </div>

        {isLoading ? (
          <div className="animate-pulse">
            {[1, 2].map(i => (
              <div key={i} style={{ height: 12, background: "rgba(255,255,255,0.06)", borderRadius: 4, marginBottom: 8 }} />
            ))}
          </div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.08em", color: "var(--tx-4)" }}>PREMIEANDEL (PVR)</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: pvrColor, fontVariantNumeric: "tabular-nums" }}>
                {pvr !== null && pvr !== undefined ? pvr.toFixed(2) : "—"}
                {pvr !== null && pvr !== undefined && pvr >= 1.0 ? " ↑" : ""}
              </span>
            </div>
            <TicketRow
              label="SNITT FOLKEAVVIK"
              value={avgEdge !== null
                ? `${avgEdge > 0 ? "+" : avgEdge < 0 ? "−" : ""}${Math.abs(avgEdge).toFixed(1)}pp`
                : "—"}
              highlight={avgEdge !== null && avgEdge > 0}
            />
          </>
        )}
      </div>

      <TicketDivider />

      {/* CTA */}
      <div style={{ padding: "0 20px 20px" }}>
        <Link href="/signaler" style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 8, padding: "13px 20px", borderRadius: 10,
          background: "var(--gold)", color: "#0a0a0b",
          fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 700,
          textDecoration: "none", letterSpacing: "-0.01em",
          transition: "opacity 0.15s ease",
        }}>
          Se signaler →
        </Link>
        <div style={{
          marginTop: 10, textAlign: "center",
          fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--tx-4)", lineHeight: 1.4,
        }}>
          Kupongen genereres og lagres automatisk
        </div>
      </div>
    </div>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({ weekLabel, isConnected, coupons, selectedId, onSelect }: {
  weekLabel: string; isConnected: boolean;
  coupons: CouponListItem[]; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20,
      background: "var(--surf-0)", borderBottom: "1px solid rgba(255,255,255,0.06)",
      height: 44, display: "flex", alignItems: "center", padding: "0 40px", gap: 14,
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: "var(--gold)" }}>
        KUPONG-INTELLIGENS
      </span>
      <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.10)", flexShrink: 0 }} />
      {weekLabel && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
          {weekLabel}
        </span>
      )}
      {coupons.length > 1 && (
        <>
          <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.10)", flexShrink: 0 }} />
          <div style={{ maxWidth: 280 }}>
            <CouponSelector
              coupons={coupons}
              selected={selectedId}
              onSelect={onSelect}
              isLoading={false}
            />
          </div>
        </>
      )}
      <div style={{ flex: 1 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span className="relative flex" style={{ width: 6, height: 6 }}>
          {isConnected && (
            <span className="animate-ping absolute inset-0 rounded-full" style={{ background: "var(--green)", opacity: 0.4 }} />
          )}
          <span className="relative rounded-full" style={{
            width: 6, height: 6,
            background: isConnected ? "var(--green)" : "var(--red)",
          }} />
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
          {isConnected ? "LIVE" : "OFFLINE"}
        </span>
      </div>
    </header>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function ContentSkeleton() {
  return (
    <div className="animate-pulse" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} style={{
          padding: "16px 18px", borderRadius: 12,
          background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.05)",
        }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
            <div style={{ height: 13, flex: 1, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
            <div style={{ width: 28, height: 28, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
          </div>
          <div style={{ height: 8, width: "60%", borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
        </div>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function KupongPage() {
  const [selectedCouponId, setSelectedCouponId] = useState<string | null>(null);
  const [strategy, setStrategy]                 = useState<Strategy>("balanced");
  const [sliderPos, setSliderPos]               = useState<number>(50);
  const [budget, setBudget]                     = useState<number>(192);
  const queryClient   = useQueryClient();
  const prevNtRef     = useRef<string | null>(null);
  const stratDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const couponsQuery = useQuery({
    queryKey: ["coupons"], queryFn: () => getCoupons(),
    staleTime: 5 * 60_000, retry: 1,
  });
  useEffect(() => {
    if (couponsQuery.data?.length && !selectedCouponId)
      setSelectedCouponId(couponsQuery.data[0].coupon_id);
  }, [couponsQuery.data, selectedCouponId]);

  const currentCoupon  = couponsQuery.data?.find(c => c.coupon_id === selectedCouponId);
  const deadlineSecs   = secsUntil(currentCoupon?.deadline_utc);
  const isOffline      = couponsQuery.isError;
  const weekLabel      = currentCoupon ? `UKE ${currentCoupon.week} / ${currentCoupon.year}` : "";

  const [syncMs, setSyncMs] = useState<number | false>(120_000);
  const syncQuery = useQuery({
    queryKey: ["sync-status"], queryFn: () => getSyncStatus(),
    staleTime: 0, retry: 1, refetchInterval: syncMs,
  });
  useEffect(() => {
    if (isOffline) { setSyncMs(30_000); return; }
    setSyncMs(syncInterval(syncQuery.data?.is_running ?? false, isFinite(deadlineSecs) ? deadlineSecs : Infinity));
  }, [isOffline, syncQuery.data?.is_running, deadlineSecs]);
  useEffect(() => {
    const nt = syncQuery.data?.last_nt_refresh_at ?? null;
    if (nt && nt !== prevNtRef.current) {
      if (prevNtRef.current !== null) queryClient.invalidateQueries({ queryKey: ["optimize"] });
      prevNtRef.current = nt;
    }
  }, [syncQuery.data?.last_nt_refresh_at, queryClient]);

  const optimizeQuery = useQuery({
    queryKey: ["optimize", selectedCouponId, strategy, budget],
    queryFn:  () => optimize({ coupon_id: selectedCouponId!, strategy, budget, cost_per_row: 1.0 }),
    enabled:  !!selectedCouponId && !isOffline,
    staleTime: 60_000, retry: 1,
    refetchInterval: isFinite(deadlineSecs) ? optimizeInterval(deadlineSecs) : false,
  });

  const enrichmentQuery = useQuery({
    queryKey: ["enrichment", selectedCouponId],
    queryFn:  () => getEnrichment(selectedCouponId!),
    enabled:  !!selectedCouponId && !isOffline,
    staleTime: 10 * 60_000, retry: 1,
  });
  const enrichmentMap = useMemo(() => new Map<number, MatchEnrichment>(
    (enrichmentQuery.data ?? []).map(e => [e.match_number, e])
  ), [enrichmentQuery.data]);

  function handleSlider(pos: number) {
    setSliderPos(pos);
    if (stratDebounce.current) clearTimeout(stratDebounce.current);
    stratDebounce.current = setTimeout(() => setStrategy(sliderToStrategy(pos)), 400);
  }

  const result     = optimizeQuery.data;
  const isLoading  = optimizeQuery.isLoading || (optimizeQuery.isFetching && !result);

  const singles  = result?.matches.filter(m => m.coverage_type === "single")     ?? [];
  const halvdekk = result?.matches.filter(m => m.coverage_type === "half_cover") ?? [];
  const heldekk  = result?.matches.filter(m => m.coverage_type === "full_cover") ?? [];

  return (
    <div className="min-h-screen" style={{ marginLeft: 240, background: "var(--canvas)" }}>
      <TopBar
        weekLabel={weekLabel}
        isConnected={!isOffline}
        coupons={couponsQuery.data ?? []}
        selectedId={selectedCouponId}
        onSelect={setSelectedCouponId}
      />

      <main style={{ maxWidth: 1160, margin: "0 auto", padding: "28px 40px 64px" }}>
        {/* Page title */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={{
            fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 800,
            color: "var(--tx-1)", letterSpacing: "-0.03em", margin: "0 0 6px 0",
          }}>
            Kupongbygger
          </h1>
          <p style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)", margin: 0 }}>
            Modellen optimaliserer dekningsstrukturen innenfor ditt budsjett og valgte profil.
          </p>
        </div>

        {isOffline && (
          <div style={{
            marginBottom: 20, padding: "12px 16px", borderRadius: 10,
            border: "1px solid rgba(200,85,78,0.20)", background: "rgba(200,85,78,0.06)",
            fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--red)",
          }}>
            Backend kjører ikke — start serveren på port 8000.
          </div>
        )}

        {/* Two-column layout */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: 28,
          alignItems: "start",
        }}>
          {/* Left: controls + coupon */}
          <div>
            <ConfigPanel
              budget={budget}
              onBudget={setBudget}
              sliderPos={sliderPos}
              onSlider={handleSlider}
            />

            {!selectedCouponId && !isOffline ? (
              <div style={{ padding: "60px 0", textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 17, fontWeight: 700, color: "var(--tx-2)", marginBottom: 8 }}>
                  Ingen aktive kuponger
                </div>
                <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                  Kjør synkronisering for å hente ukens kamper.
                </div>
              </div>
            ) : isLoading ? (
              <ContentSkeleton />
            ) : result ? (
              <>
                {/* Summary line */}
                <div style={{ marginBottom: 20, padding: "12px 16px", background: "var(--surf-1)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.06)" }}>
                  <div style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-2)", lineHeight: 1.5 }}>
                    {(() => {
                      const strong = result.matches.filter(m => (edgePp(m) ?? 0) >= 8);
                      if (strong.length >= 3) return `${strong.length} kamper der modellen ser klar verdi mot folkemengden.`;
                      if (strong.length >= 1) return `${strong.length} kamp${strong.length > 1 ? "er" : ""} der modellen ser klar verdi mot folkemengden.`;
                      return "Kupongen er optimalisert for best mulig forventet verdi innenfor budsjettet.";
                    })()}
                  </div>
                </div>

                <GroupSection slug="single"     matches={singles}  enrichmentMap={enrichmentMap} baseDelay={0} />
                <GroupSection slug="half_cover" matches={halvdekk} enrichmentMap={enrichmentMap} baseDelay={0.1} />
                <GroupSection slug="full_cover" matches={heldekk}  enrichmentMap={enrichmentMap} baseDelay={0.2} />
              </>
            ) : null}
          </div>

          {/* Right: ticket card */}
          <TicketCard
            result={result}
            strategy={strategy}
            budget={budget}
            isLoading={isLoading}
          />
        </div>
      </main>
    </div>
  );
}
