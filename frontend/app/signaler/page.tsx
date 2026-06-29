"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import Link from "next/link";
import { getSignalBoard, getEnrichment } from "@/lib/api";
import type { MatchSignal, MatchEnrichment } from "@/lib/types";
import { formatUntil } from "@/lib/utils";

const EASE = [0.16, 1, 0.3, 1] as const;

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtTime(utc: string | null): string {
  if (!utc) return "";
  try { return new Date(utc).toLocaleTimeString("no", { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

function pickName(pick: string): string {
  return ({ H: "Hjemme", U: "Uavgjort", B: "Borte" }[pick] ?? pick);
}

function classLabel(cls: string): string {
  return (
    { banker: "Banker", uncertain: "Usikker", half_cover: "Halvdekk", full_cover: "Heldekk", standard: "Standard" }[cls] ?? cls
  );
}

function countChar(s: string | null | undefined, c: string): number {
  return (s ?? "").split("").filter(ch => ch === c).length;
}

function parseVenueRecord(s: string | null): { wins: number; draws: number; losses: number; played: number } | null {
  if (!s) return null;
  const w = parseInt(s.match(/W(\d+)/i)?.[1] ?? "0");
  const d = parseInt(s.match(/D(\d+)/i)?.[1] ?? "0");
  const l = parseInt(s.match(/L(\d+)/i)?.[1] ?? "0");
  const played = w + d + l;
  if (played === 0) return null;
  return { wins: w, draws: d, losses: l, played };
}

// ── Signal interpretation ─────────────────────────────────────────────────────

function buildSignalInterpretation(
  signal: MatchSignal, home: string, away: string
): { headline: string; explanation: string; action: string } {
  const pick  = signal.recommended_pick;
  const edge  = signal.edge_pp;
  const model = signal.model_prob;
  const crowd = signal.pub_prob;
  const teamName  = pick === "H" ? home : pick === "B" ? away : null;
  const pickLabel = teamName ?? "uavgjort";

  if (!signal.has_public_tips || edge === null || crowd === null) {
    const conf = model >= 65 ? "sterk" : model >= 55 ? "god" : "moderat";
    return {
      headline:    `Modellen har ${conf} tro på ${pick === "U" ? "uavgjort" : pickLabel}`,
      explanation: `Anbefaling basert på bookmaker-odds og statistikk. Norsk Tipping-spillertall er ikke tilgjengelig for denne kampen.`,
      action:      `Inkluder ${pick === "U" ? "uavgjort" : pickLabel} i kupongen.`,
    };
  }

  const crowdRound = Math.round(crowd);

  if (edge >= 10) return {
    headline:    `${pick === "U" ? "Uavgjort" : pickLabel} er undervurdert av Norsk Tipping-spillerne`,
    explanation: `${crowdRound}% av spillerne velger ${pickLabel}. Modellen mener den faktiske sannsynligheten er nærmere ${model}% — et klart avvik som gir positiv forventet verdi i pool-spillet.`,
    action:      `Dette er en av ukens beste muligheter. ${pickLabel} er modellens sterkeste anbefaling.`,
  };
  if (edge >= 4) return {
    headline:    `Modellen ser mer verdi her enn folkemengden`,
    explanation: `${crowdRound}% velger ${pickLabel}. Modellen anslår ${model}% — et avvik som er konsekvent nok til å gi en statistisk fordel.`,
    action:      `Ta med ${pickLabel} i kupongen. Avviket er ikke dramatisk, men det er reelt nok til å anbefales.`,
  };
  if (edge > -4) return {
    headline:    `Modellen og spillerne er relativt enige`,
    explanation: `${crowdRound}% velger ${pickLabel}, modellen anslår ${model}%. Ingen sterk verdikant, men utfallet styrker kupongstrukturen som helhet.`,
    action:      `Inkluder ${pickLabel} i kupongen — det er ikke en verdikamp, men det gjør kupongen mer balansert.`,
  };
  if (edge > -10) return {
    headline:    `${pick === "U" ? "Uavgjort" : pickLabel} er populær — modellen er mer avventende`,
    explanation: `${crowdRound}% velger ${pickLabel}, men modellen anslår kun ${model}%. Kupongens dekningsstruktur kompenserer for usikkerheten.`,
    action:      `Kupongen dekker usikkerheten her. Sjekk om kampen er satt til halvdekk eller heldekk.`,
  };
  return {
    headline:    `Mange spillere velger ${pickLabel} — modellen er skeptisk`,
    explanation: `Hele ${crowdRound}% velger ${pickLabel}. Modellen anslår kun ${model}%. Folkemengden er langt mer optimistisk enn hva oddsen tilsier.`,
    action:      `Kupongens halvdekk- eller heldekk-struktur dekker usikkerheten her. Ikke spill singel på dette utfallet.`,
  };
}

// ── Insight derivation ────────────────────────────────────────────────────────

type Insight = { text: string };

function deriveInsights(
  signal: MatchSignal,
  enrichment: MatchEnrichment | null
): { supporting: Insight[]; risks: Insight[] } {
  const supporting: Insight[] = [];
  const risks: Insight[] = [];
  const pick = signal.recommended_pick;
  const home = enrichment?.home_team ?? signal.home_team;
  const away = enrichment?.away_team ?? signal.away_team;

  const add = (direction: "H" | "B", text: string) => {
    if (pick === "U") { risks.push({ text }); }
    else if (direction === pick) { supporting.push({ text }); }
    else { risks.push({ text }); }
  };

  if (enrichment) {
    if (signal.stats_signals.includes("form")) {
      const homeW = countChar(enrichment.home_last_5, "W");
      const awayW = countChar(enrichment.away_last_5, "W");
      const diff  = homeW - awayW;
      if (diff >= 2) add("H", `${home} vant ${homeW} av siste 5 kamper (${away}: ${awayW})`);
      else if (diff <= -2) add("B", `${away} i bedre form — vant ${awayW} av 5 (${home}: ${homeW})`);
      else if (diff === 1) add("H", `${home} noe bedre form siste 5 kamper`);
      else if (diff === -1) add("B", `${away} noe bedre form siste 5 kamper`);
      else if (pick === "U") supporting.push({ text: `Jevnt formduel — ${homeW} vs ${awayW} seire av siste 5` });
    }

    if (signal.stats_signals.includes("h_a_record")) {
      const homeRec = parseVenueRecord(enrichment.home_home_record);
      const awayRec = parseVenueRecord(enrichment.away_away_record);
      if (homeRec && homeRec.played >= 2) {
        const pct = homeRec.wins / homeRec.played;
        if (pct >= 0.6) add("H", `${home} sterk hjemme: ${homeRec.wins}V ${homeRec.draws}U ${homeRec.losses}T`);
        else if (pct <= 0.25 && homeRec.played >= 3) add("B", `${home} svak hjemme denne sesongen (${homeRec.wins}V ${homeRec.losses}T)`);
      }
      if (awayRec && awayRec.played >= 2) {
        const pct = awayRec.wins / awayRec.played;
        if (pct >= 0.6) add("B", `${away} sterk på bortebane: ${awayRec.wins}V ${awayRec.draws}U ${awayRec.losses}T`);
        else if (pct <= 0.25 && awayRec.played >= 3) add("H", `${away} svak på bortebane (${awayRec.wins}V ${awayRec.losses}T)`);
      }
    }

    if (signal.stats_signals.includes("goals")) {
      const hGF = enrichment.home_avg_goals_for;
      const aGF = enrichment.away_avg_goals_for;
      const hGA = enrichment.home_avg_goals_against;
      const aGA = enrichment.away_avg_goals_against;
      if (hGF != null && aGF != null && Math.abs(hGF - aGF) >= 0.4) {
        if (hGF > aGF) add("H", `${home} scorer ${hGF.toFixed(1)} mål/kamp — ${away} ${aGF.toFixed(1)}`);
        else add("B", `${away} scorer ${aGF.toFixed(1)} mål/kamp — ${home} ${hGF.toFixed(1)}`);
      }
      if (hGA != null && aGA != null && Math.abs(hGA - aGA) >= 0.5) {
        if (aGA > hGA) add("H", `${away}s forsvar slipper inn ${aGA.toFixed(1)} mål/kamp`);
        else add("B", `${home}s forsvar slipper inn ${hGA.toFixed(1)} mål/kamp`);
      }
    }

    if (signal.stats_signals.includes("standings")) {
      const hPos = enrichment.home_position;
      const aPos = enrichment.away_position;
      if (hPos != null && aPos != null) {
        const diff = aPos - hPos;
        if (diff >= 4) add("H", `${home} er ${diff} plasser høyere på tabellen (${hPos} vs ${aPos})`);
        else if (diff <= -4) add("B", `${away} er ${Math.abs(diff)} plasser høyere på tabellen (${aPos} vs ${hPos})`);
      }
    }

    if (signal.stats_signals.includes("xg")) {
      const hXG = enrichment.home_recent_fixture_stats?.avg_xg;
      const aXG = enrichment.away_recent_fixture_stats?.avg_xg;
      if (hXG != null && aXG != null && Math.abs(hXG - aXG) >= 0.25) {
        if (hXG > aXG) add("H", `xG-trend: ${home} dominerer (${hXG.toFixed(1)} vs ${aXG.toFixed(1)})`);
        else add("B", `xG-trend: ${away} dominerer (${aXG.toFixed(1)} vs ${hXG.toFixed(1)})`);
      }
    }
  }

  if (signal.has_public_tips && signal.pub_prob != null && signal.edge_pp != null) {
    const pubPct   = signal.pub_prob.toFixed(0);
    const modelPct = signal.model_prob.toFixed(0);
    const pickLabel = pick === "H" ? home : pick === "B" ? away : "uavgjort";
    if (signal.edge_pp >= 5) {
      supporting.push({ text: `Folkemengden undervurderer ${pickLabel}: ${pubPct}% vs modellens ${modelPct}%` });
    } else if (signal.edge_pp <= -5) {
      risks.push({ text: `Folkemengden er mer overbevist enn modellen — ${pubPct}% vs ${modelPct}%` });
    }
  }

  return { supporting, risks };
}

// ── Team logo with initials fallback ─────────────────────────────────────────

function TeamLogo({ name, url, size = 48 }: { name: string; url?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const initials = name.split(/\s+/).map(w => w[0]).join("").slice(0, 2).toUpperCase();
  const hue = Array.from(name).reduce((h, c) => (h * 31 + c.charCodeAt(0)) & 0xFFFF, 0) % 360;
  const showFallback = !url || failed;

  return (
    <div style={{
      width: size, height: size, borderRadius: 5,
      background: showFallback ? `hsl(${hue}, 28%, 18%)` : "transparent",
      overflow: "hidden",
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0,
    }}>
      {!showFallback ? (
        <img src={url!} alt={name} width={size} height={size}
             style={{ objectFit: "contain", padding: size * 0.1 }}
             onError={() => setFailed(true)} />
      ) : (
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: size * 0.28, fontWeight: 700,
          color: `hsl(${hue}, 55%, 68%)`, letterSpacing: "-0.02em",
        }}>
          {initials}
        </span>
      )}
    </div>
  );
}

// ── Comparison bar (model vs crowd) ──────────────────────────────────────────

function CompBar({ label, pct, crowd, model, isModel, delay }: {
  label: string; pct: number; crowd: number; model: number; isModel: boolean; delay: number;
}) {
  const edge = model - crowd;
  const edgePos = edge >= 0;
  const h = 7;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 500,
        letterSpacing: "0.08em", color: "var(--tx-3)",
        width: 54, flexShrink: 0,
      }}>{label}</span>
      <div style={{
        flex: 1, height: h, borderRadius: h / 2,
        background: "rgba(255,255,255,0.06)", position: "relative", overflow: "hidden",
      }}>
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: isModel ? Math.min(crowd, model) / 100 : pct / 100 }}
          transition={{ duration: 0.58, delay, ease: [0, 0, 0.2, 1] }}
          style={{
            position: "absolute", inset: 0, width: "100%",
            background: isModel ? "var(--tx-1)" : "rgba(255,255,255,0.20)",
            borderRadius: h / 2, transformOrigin: "left",
          }}
        />
        {isModel && edgePos && (
          <motion.div
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.44, delay: delay + 0.44, ease: EASE }}
            style={{
              position: "absolute", left: `${crowd}%`, top: 0, bottom: 0,
              width: `${edge}%`,
              background: "var(--gold)", borderRadius: "0 999px 999px 0", opacity: 0.9,
              transformOrigin: "left",
            }}
          />
        )}
        {!isModel && !edgePos && (
          <motion.div
            initial={{ scaleX: 0, opacity: 0 }}
            animate={{ scaleX: 1, opacity: 1 }}
            transition={{ duration: 0.38, delay: delay + 0.38 }}
            style={{
              position: "absolute", left: `${model}%`, top: 0, bottom: 0,
              width: `${Math.abs(edge)}%`,
              background: "rgba(123,146,255,0.45)", borderRadius: "0 999px 999px 0",
              transformOrigin: "left",
            }}
          />
        )}
      </div>
      <span style={{
        fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: isModel ? 700 : 500,
        color: isModel ? "var(--tx-1)" : "var(--tx-2)",
        width: 32, textAlign: "right", fontVariantNumeric: "tabular-nums", flexShrink: 0,
      }}>{pct}%</span>
    </div>
  );
}

// ── Form pips ─────────────────────────────────────────────────────────────────

function FormPips({ form }: { form: string | null }) {
  const chars = (form ?? "").slice(-5).split("").filter(c => c === "W" || c === "D" || c === "L");
  if (chars.length === 0) return null;
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
      {chars.map((c, i) => (
        <span key={i} style={{
          display: "inline-block", width: 7, height: 7, borderRadius: "50%",
          background: c === "W" ? "var(--green)" : c === "D" ? "var(--gold)" : "var(--red)",
          flexShrink: 0,
        }} />
      ))}
    </div>
  );
}

// ── Featured signal card ──────────────────────────────────────────────────────

function FeaturedCard({ signal, enrichment }: {
  signal: MatchSignal; enrichment: MatchEnrichment | null;
}) {
  const hasCrowd = signal.has_public_tips && signal.pub_prob !== null;
  const edge = signal.edge_pp;
  const crowd = signal.pub_prob ?? 0;
  const model = signal.model_prob;
  const isPos = (edge ?? 0) >= 0;
  const home = enrichment?.home_team ?? signal.home_team;
  const away = enrichment?.away_team ?? signal.away_team;

  const insights = deriveInsights(signal, enrichment);
  const interpretation = buildSignalInterpretation(signal, home, away);
  const time = fmtTime(signal.kickoff_utc);
  const hasInsights = insights.supporting.length > 0 || insights.risks.length > 0;
  const isBigEdge = hasCrowd && (edge ?? 0) >= 8;

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE }}
      style={{
        background: "var(--surf-1)",
        border: `1px solid ${isBigEdge ? "rgba(201,160,74,0.22)" : "rgba(255,255,255,0.08)"}`,
        borderRadius: 20, overflow: "hidden",
        boxShadow: isBigEdge ? "0 0 40px rgba(201,160,74,0.04)" : "none",
      }}
    >
      {/* Label strip */}
      <div style={{
        padding: "10px 32px",
        borderBottom: "1px solid rgba(255,255,255,0.06)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700,
          letterSpacing: "0.14em", color: "var(--gold)",
        }}>KUPONG-INTELLIGENS · STERKESTE SIGNAL DENNE UKEN</span>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.06em",
          background: "rgba(255,255,255,0.05)", borderRadius: 4, padding: "2px 8px",
          color: "var(--tx-4)",
        }}>
          {classLabel(signal.classification).toUpperCase()}
        </span>
      </div>

      {/* Match header */}
      <div style={{ padding: "28px 32px 20px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 14 }}>
          {/* Home team */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <TeamLogo name={home} url={enrichment?.home_logo_url} size={52} />
            <div>
              <div style={{
                fontFamily: "var(--font-heading)", fontSize: 20, fontWeight: 800,
                color: "var(--tx-1)", letterSpacing: "-0.025em", lineHeight: 1.15,
              }}>{home}</div>
              {enrichment?.home_last_5 && (
                <div style={{ marginTop: 5 }}>
                  <FormPips form={enrichment.home_last_5} />
                </div>
              )}
            </div>
          </div>

          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--tx-4)",
            padding: "0 12px", flexShrink: 0,
          }}>vs</span>

          {/* Away team */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{
                fontFamily: "var(--font-heading)", fontSize: 20, fontWeight: 800,
                color: "var(--tx-1)", letterSpacing: "-0.025em", lineHeight: 1.15,
              }}>{away}</div>
              {enrichment?.away_last_5 && (
                <div style={{ marginTop: 5, display: "flex", justifyContent: "flex-end" }}>
                  <FormPips form={enrichment.away_last_5} />
                </div>
              )}
            </div>
            <TeamLogo name={away} url={enrichment?.away_logo_url} size={52} />
          </div>
        </div>

        {/* Meta row */}
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {signal.league_name && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--tx-4)", letterSpacing: "0.05em" }}>
              {signal.league_name}
            </span>
          )}
          {time && (
            <>
              <span style={{ color: "rgba(255,255,255,0.14)", fontSize: 10 }}>·</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--tx-4)", letterSpacing: "0.04em" }}>
                {time}
              </span>
            </>
          )}
        </div>
      </div>

      <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }} />

      {/* Content — two columns */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "1fr 300px",
      }}>
        {/* Left: narrative + insights */}
        <div style={{ padding: "28px 32px" }}>
          <h2 style={{
            fontFamily: "var(--font-heading)", fontSize: 21, fontWeight: 800,
            color: "var(--tx-1)", letterSpacing: "-0.025em", lineHeight: 1.3,
            margin: "0 0 14px 0",
          }}>
            {interpretation.headline}
          </h2>

          <p style={{
            fontFamily: "var(--font-sans)", fontSize: 15, color: "var(--tx-2)",
            lineHeight: 1.7, margin: "0 0 20px 0",
          }}>
            {interpretation.explanation}
          </p>

          {hasInsights && (
            <div style={{ display: "flex", flexDirection: "column", gap: 9, marginBottom: 20 }}>
              {insights.supporting.map((ins, i) => (
                <div key={`s${i}`} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span style={{ color: "var(--green)", fontSize: 12, lineHeight: "22px", flexShrink: 0 }}>✓</span>
                  <span style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-2)", lineHeight: 1.5 }}>
                    {ins.text}
                  </span>
                </div>
              ))}
              {insights.risks.map((ins, i) => (
                <div key={`r${i}`} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <span style={{ color: "var(--gold)", fontSize: 12, lineHeight: "22px", flexShrink: 0 }}>⚠</span>
                  <span style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-2)", lineHeight: 1.5 }}>
                    {ins.text}
                  </span>
                </div>
              ))}
            </div>
          )}

          {interpretation.action && (
            <p style={{
              fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)",
              lineHeight: 1.6, margin: "0 0 24px 0", fontStyle: "italic",
            }}>
              {interpretation.action}
            </p>
          )}

          <Link href="/kupong" style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 600,
            color: "var(--gold)", textDecoration: "none",
          }}>
            Gå til kupong →
          </Link>
        </div>

        {/* Right: edge + bars + recommendation */}
        <div style={{
          padding: "28px 28px",
          borderLeft: "1px solid rgba(255,255,255,0.06)",
          display: "flex", flexDirection: "column",
        }}>
          {/* Big edge number */}
          <div style={{ marginBottom: 6 }}>
            <div style={{
              fontFamily: "var(--font-heading)", fontWeight: 900,
              fontSize: "clamp(52px, 5.5vw, 68px)", lineHeight: 1,
              letterSpacing: "-0.055em", fontVariantNumeric: "tabular-nums",
              color: !hasCrowd ? "var(--tx-3)" : isPos ? "var(--gold)" : "var(--indigo)",
            }}>
              {hasCrowd && edge !== null
                ? `${edge > 0 ? "+" : ""}${Math.abs(edge).toFixed(1)}pp`
                : `${model}%`}
            </div>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.13em", color: "var(--tx-4)", marginTop: 7,
            }}>
              {hasCrowd
                ? edge !== null && edge > 0 ? "UNDERPRISET AV FOLKET" : edge !== null && edge < 0 ? "OVERPRISET AV FOLKET" : "JEVNT"
                : "MODELL-SANNSYNLIGHET"}
            </div>
          </div>

          <div style={{ flex: 1 }} />

          {/* Probability comparison */}
          {hasCrowd ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 20 }}>
              <CompBar label="FOLKET" pct={Math.round(crowd)} crowd={crowd} model={model} isModel={false} delay={0.1} />
              <CompBar label="MODELL" pct={Math.round(model)} crowd={crowd} model={model} isModel={true} delay={0.1} />
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 20 }}>
              {[
                { label: "HJEMME", val: signal.prob_h, isRec: signal.recommended_pick === "H" },
                { label: "UAVGJORT", val: signal.prob_u, isRec: signal.recommended_pick === "U" },
                { label: "BORTE", val: signal.prob_b, isRec: signal.recommended_pick === "B" },
              ].map(({ label, val, isRec }, idx) => (
                <div key={label} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.06em",
                    color: isRec ? "var(--tx-2)" : "var(--tx-4)", width: 60, flexShrink: 0,
                  }}>{label}</span>
                  <div style={{
                    flex: 1, height: 6, borderRadius: 3,
                    background: "rgba(255,255,255,0.06)", overflow: "hidden", position: "relative",
                  }}>
                    <motion.div
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: val / 100 }}
                      transition={{ duration: 0.55, delay: idx * 0.07, ease: [0, 0, 0.2, 1] }}
                      style={{
                        position: "absolute", inset: 0, width: "100%",
                        background: isRec ? "var(--tx-1)" : "rgba(255,255,255,0.14)",
                        borderRadius: 3, transformOrigin: "left",
                      }}
                    />
                  </div>
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: isRec ? 700 : 500,
                    color: isRec ? "var(--tx-1)" : "var(--tx-3)",
                    width: 32, textAlign: "right", fontVariantNumeric: "tabular-nums",
                  }}>{val}%</span>
                </div>
              ))}
            </div>
          )}

          {/* Recommendation chip */}
          <div style={{
            padding: "12px 14px",
            background: "rgba(255,255,255,0.04)",
            borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)",
          }}>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em",
              color: "var(--tx-4)", marginBottom: 8,
            }}>ANBEFALING</div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: 26, height: 26, borderRadius: 7,
                background: "rgba(255,255,255,0.08)", border: "1px solid rgba(255,255,255,0.12)",
                fontFamily: "var(--font-heading)", fontSize: 12, fontWeight: 700, color: "var(--tx-1)",
                flexShrink: 0,
              }}>{signal.recommended_pick}</span>
              <span style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-2)" }}>
                {pickName(signal.recommended_pick)} · {model}%
                {hasCrowd && ` / ${Math.round(crowd)}% folket`}
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Signal grid card ──────────────────────────────────────────────────────────

function SignalCard({ signal, enrichment, delay = 0 }: {
  signal: MatchSignal; enrichment: MatchEnrichment | null; delay?: number;
}) {
  const hasCrowd = signal.has_public_tips && signal.pub_prob !== null;
  const edge = signal.edge_pp;
  const crowd = signal.pub_prob ?? 0;
  const model = signal.model_prob;
  const isPos = (edge ?? 0) >= 0;
  const home = enrichment?.home_team ?? signal.home_team;
  const away = enrichment?.away_team ?? signal.away_team;
  const interpretation = buildSignalInterpretation(signal, home, away);
  const time = fmtTime(signal.kickoff_utc);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: EASE }}
      whileHover={{ y: -2 }}
      style={{
        background: "var(--surf-1)",
        border: "1px solid rgba(255,255,255,0.07)",
        borderRadius: 16, overflow: "hidden",
        transition: "border-color 0.15s ease",
        cursor: "default",
      }}
    >
      {/* Match header */}
      <div style={{ padding: "18px 20px 14px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <TeamLogo name={home} url={enrichment?.home_logo_url} size={30} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>vs</span>
          <TeamLogo name={away} url={enrichment?.away_logo_url} size={30} />
          <div style={{ flex: 1 }} />
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em",
            color: "var(--tx-4)", background: "rgba(255,255,255,0.05)",
            borderRadius: 4, padding: "2px 6px",
          }}>
            {classLabel(signal.classification).toUpperCase()}
          </span>
        </div>

        <div style={{
          fontFamily: "var(--font-heading)", fontSize: 14, fontWeight: 700,
          color: "var(--tx-1)", letterSpacing: "-0.02em", lineHeight: 1.2, marginBottom: 3,
        }}>
          {home} – {away}
        </div>
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)",
          letterSpacing: "0.04em",
        }}>
          {[signal.league_name, time].filter(Boolean).join(" · ")}
        </div>
      </div>

      <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }} />

      {/* Edge + headline */}
      <div style={{ padding: "14px 20px 12px" }}>
        <div style={{
          fontFamily: "var(--font-heading)", fontWeight: 900,
          fontSize: 34, lineHeight: 1, letterSpacing: "-0.04em",
          fontVariantNumeric: "tabular-nums",
          color: !hasCrowd ? "var(--tx-3)" : isPos ? "var(--gold)" : "var(--indigo)",
          marginBottom: 6,
        }}>
          {hasCrowd && edge !== null
            ? `${isPos ? "+" : ""}${Math.abs(edge).toFixed(1)}pp`
            : `${model}%`}
        </div>
        <p style={{
          fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-3)",
          lineHeight: 1.5, margin: 0,
          display: "-webkit-box",
          WebkitLineClamp: 2,
          WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}>
          {interpretation.headline}
        </p>
      </div>

      {/* Bars */}
      {hasCrowd && (
        <div style={{ padding: "0 20px 14px", display: "flex", flexDirection: "column", gap: 7 }}>
          <CompBar label="FOLKET" pct={Math.round(crowd)} crowd={crowd} model={model} isModel={false} delay={delay} />
          <CompBar label="MODELL" pct={Math.round(model)} crowd={crowd} model={model} isModel={true} delay={delay} />
        </div>
      )}

      <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)" }} />

      {/* Footer */}
      <div style={{
        padding: "10px 20px",
        display: "flex", alignItems: "center", gap: 8,
      }}>
        <span style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 22, height: 22, borderRadius: 6,
          background: "rgba(255,255,255,0.07)", border: "1px solid rgba(255,255,255,0.1)",
          fontFamily: "var(--font-heading)", fontSize: 11, fontWeight: 700, color: "var(--tx-1)",
          flexShrink: 0,
        }}>{signal.recommended_pick}</span>
        <span style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-3)" }}>
          {pickName(signal.recommended_pick)}
        </span>
        <div style={{ flex: 1 }} />
        <Link href="/kupong" style={{
          fontFamily: "var(--font-sans)", fontSize: 11, fontWeight: 600,
          color: "var(--tx-4)", textDecoration: "none",
        }}>
          Les analyse →
        </Link>
      </div>
    </motion.div>
  );
}

// ── Skeleton states ───────────────────────────────────────────────────────────

function FeaturedSkeleton() {
  return (
    <div className="animate-pulse" style={{
      background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 20, overflow: "hidden",
    }}>
      <div style={{ padding: "10px 32px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div style={{ height: 9, width: 280, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
      </div>
      <div style={{ padding: "28px 32px", borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 14 }}>
          <div style={{ width: 52, height: 52, borderRadius: 5, background: "rgba(255,255,255,0.07)" }} />
          <div style={{ height: 20, width: 160, borderRadius: 6, background: "rgba(255,255,255,0.07)" }} />
          <div style={{ height: 14, width: 24, borderRadius: 4, background: "rgba(255,255,255,0.05)", margin: "0 12px" }} />
          <div style={{ width: 52, height: 52, borderRadius: 5, background: "rgba(255,255,255,0.07)" }} />
          <div style={{ height: 20, width: 160, borderRadius: 6, background: "rgba(255,255,255,0.07)" }} />
        </div>
        <div style={{ height: 10, width: 200, borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px" }}>
        <div style={{ padding: "28px 32px" }}>
          <div style={{ height: 22, width: "80%", borderRadius: 6, background: "rgba(255,255,255,0.07)", marginBottom: 12 }} />
          <div style={{ height: 22, width: "60%", borderRadius: 6, background: "rgba(255,255,255,0.07)", marginBottom: 20 }} />
          <div style={{ height: 15, width: "100%", borderRadius: 4, background: "rgba(255,255,255,0.05)", marginBottom: 8 }} />
          <div style={{ height: 15, width: "90%", borderRadius: 4, background: "rgba(255,255,255,0.05)", marginBottom: 8 }} />
          <div style={{ height: 15, width: "95%", borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
        </div>
        <div style={{
          padding: "28px 28px",
          borderLeft: "1px solid rgba(255,255,255,0.06)",
        }}>
          <div style={{ height: 64, width: 140, borderRadius: 8, background: "rgba(255,255,255,0.08)", marginBottom: 12 }} />
          <div style={{ height: 10, width: 100, borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
        </div>
      </div>
    </div>
  );
}

function GridSkeleton() {
  return (
    <div className="animate-pulse" style={{
      background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 16, overflow: "hidden",
    }}>
      <div style={{ padding: "18px 20px 14px" }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
          <div style={{ width: 30, height: 30, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
          <div style={{ width: 30, height: 30, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
        </div>
        <div style={{ height: 14, width: "70%", borderRadius: 4, background: "rgba(255,255,255,0.07)", marginBottom: 6 }} />
        <div style={{ height: 9, width: 120, borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
      </div>
      <div style={{ borderTop: "1px solid rgba(255,255,255,0.05)", padding: "14px 20px" }}>
        <div style={{ height: 34, width: 100, borderRadius: 6, background: "rgba(255,255,255,0.08)", marginBottom: 8 }} />
        <div style={{ height: 12, width: "90%", borderRadius: 4, background: "rgba(255,255,255,0.05)" }} />
      </div>
    </div>
  );
}

// ── Header ───────────────────────────────────────────────────────────────────

function PageHeader({ couponLabel, deadline, week, year, nSignals, nStrong }: {
  couponLabel: string; deadline: string;
  week: number; year: number; nSignals: number; nStrong: number;
}) {
  return (
    <header className="sticky top-0 z-20" style={{
      background: "var(--surf-0)", borderBottom: "1px solid rgba(255,255,255,0.06)",
      height: 44, display: "flex", alignItems: "center",
    }}>
      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "0 40px", width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: "var(--gold)" }}>
            KUPONG-INTELLIGENS
          </span>
          <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.1)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
            UKE {week}&nbsp;/&nbsp;{year}
          </span>
          <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.1)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
            {nSignals} KAMPER
          </span>
          {nStrong > 0 && (
            <>
              <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.1)" }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--gold)", letterSpacing: "0.06em", opacity: 0.85 }}>
                {nStrong} STERKE SIGNAL
              </span>
            </>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {deadline && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
              FRIST&nbsp;{formatUntil(deadline)}
            </span>
          )}
          <span className="relative flex" style={{ width: 6, height: 6 }}>
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full" style={{ background: "var(--green)", opacity: 0.5 }} />
            <span className="relative inline-flex rounded-full" style={{ width: 6, height: 6, background: "var(--green)" }} />
          </span>
        </div>
      </div>
    </header>
  );
}

// ── Filter chips ──────────────────────────────────────────────────────────────

type Filter = "alle" | "sterke" | "med-data";

function FilterChips({ active, onChange, signals }: {
  active: Filter; onChange: (f: Filter) => void; signals: MatchSignal[];
}) {
  const nSterke = signals.filter(s => (s.edge_pp ?? 0) >= 10).length;
  const nMedData = signals.filter(s => s.has_public_tips).length;

  const chips: { id: Filter; label: string; count: number }[] = [
    { id: "alle",     label: "Alle",         count: signals.length },
    { id: "sterke",   label: "Høy tillit",   count: nSterke },
    { id: "med-data", label: "Med kamp-data", count: nMedData },
  ];

  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 24 }}>
      {chips.map(chip => (
        <button
          key={chip.id}
          onClick={() => onChange(chip.id)}
          style={{
            fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: 500,
            padding: "5px 12px", borderRadius: 20, border: "1px solid",
            cursor: "pointer", transition: "all 0.15s ease",
            display: "flex", alignItems: "center", gap: 6,
            background: active === chip.id ? "rgba(201,160,74,0.10)" : "transparent",
            borderColor: active === chip.id ? "rgba(201,160,74,0.35)" : "rgba(255,255,255,0.10)",
            color: active === chip.id ? "var(--gold)" : "var(--tx-3)",
          }}
        >
          {chip.label}
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 9,
            color: active === chip.id ? "rgba(201,160,74,0.7)" : "var(--tx-4)",
          }}>
            {chip.count}
          </span>
        </button>
      ))}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SignalerPage() {
  const [filter, setFilter] = useState<Filter>("alle");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["signal-board"],
    queryFn: () => getSignalBoard(),
    refetchInterval: 30_000,
    retry: 2,
  });

  const { data: enrichmentData } = useQuery({
    queryKey: ["enrichment", data?.coupon_id],
    queryFn: () => getEnrichment(data!.coupon_id),
    enabled: !!data?.coupon_id,
    staleTime: 5 * 60 * 1000,
  });

  const enrichmentMap = useMemo(() => {
    const map = new Map<number, MatchEnrichment>();
    for (const e of enrichmentData ?? []) map.set(e.match_number, e);
    return map;
  }, [enrichmentData]);

  const allSignals = data?.signals ?? [];
  const nStrong    = allSignals.filter(s => (s.edge_pp ?? 0) >= 10).length;
  const featured   = allSignals[0] ?? null;

  const gridSignals = useMemo(() => {
    const rest = allSignals.slice(1);
    if (filter === "sterke") return rest.filter(s => (s.edge_pp ?? 0) >= 10);
    if (filter === "med-data") return rest.filter(s => s.has_public_tips);
    return rest;
  }, [allSignals, filter]);

  return (
    <div style={{ marginLeft: 240, background: "var(--canvas)", minHeight: "100vh" }}>
      {data ? (
        <PageHeader
          couponLabel={data.coupon_label}
          deadline={data.deadline_utc}
          week={data.week}
          year={data.year}
          nSignals={data.signals.length}
          nStrong={nStrong}
        />
      ) : (
        <div style={{ height: 44, background: "var(--surf-0)", borderBottom: "1px solid rgba(255,255,255,0.06)" }} />
      )}

      <main style={{ maxWidth: 1200, margin: "0 auto", padding: "32px 40px 64px" }}>
        {isError ? (
          <div style={{ padding: "80px 0", textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: 18, fontWeight: 700, color: "var(--tx-2)", marginBottom: 8 }}>
              Klarte ikke å laste signaler
            </div>
            <div style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)" }}>
              Sjekk at backend kjører på port 8000.
            </div>
          </div>
        ) : isLoading ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
            <FeaturedSkeleton />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
              {Array.from({ length: 4 }).map((_, i) => <GridSkeleton key={i} />)}
            </div>
          </div>
        ) : !data || allSignals.length === 0 ? (
          <div style={{ padding: "80px 0", textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: 18, fontWeight: 700, color: "var(--tx-2)", marginBottom: 8 }}>
              Ingen aktive kuponger denne uken
            </div>
            <div style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)" }}>
              Kjør synkronisering for å hente ukens kamper.
            </div>
          </div>
        ) : (
          <>
            {/* Page title */}
            <div style={{ marginBottom: 28 }}>
              <h1 style={{
                fontFamily: "var(--font-heading)", fontSize: 26, fontWeight: 800,
                color: "var(--tx-1)", letterSpacing: "-0.03em", margin: "0 0 6px 0",
              }}>
                Ukens analyse
              </h1>
              <p style={{
                fontFamily: "var(--font-sans)", fontSize: 15, color: "var(--tx-3)",
                margin: 0, lineHeight: 1.5,
              }}>
                {nStrong > 0
                  ? `Modellen fant ${nStrong} signal${nStrong !== 1 ? "er" : ""} med klart avvik mot folkemengden denne uken.`
                  : `${allSignals.length} kamper analysert. Alle odds og folkestemmer oppdateres automatisk.`}
              </p>
            </div>

            {/* Featured card */}
            {featured && (
              <div style={{ marginBottom: 40 }}>
                <FeaturedCard
                  signal={featured}
                  enrichment={enrichmentMap.get(featured.match_number) ?? null}
                />
              </div>
            )}

            {/* Grid signals */}
            {gridSignals.length > 0 && (
              <>
                <div style={{ marginBottom: 20, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <div style={{
                    fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                    letterSpacing: "0.14em", color: "var(--tx-4)",
                  }}>
                    ØVRIGE KAMPER · RANGERT ETTER SIGNALSTYRKE
                  </div>
                  <FilterChips active={filter} onChange={setFilter} signals={allSignals.slice(1)} />
                </div>

                <div style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(310px, 1fr))",
                  gap: 16,
                }}>
                  {gridSignals.map((signal, i) => (
                    <SignalCard
                      key={signal.match_number}
                      signal={signal}
                      enrichment={enrichmentMap.get(signal.match_number) ?? null}
                      delay={i * 0.05}
                    />
                  ))}
                </div>
              </>
            )}

            {/* CTA footer */}
            <div style={{
              marginTop: 48, padding: "28px 32px",
              background: "var(--surf-1)", borderRadius: 16,
              border: "1px solid rgba(255,255,255,0.07)",
              display: "flex", alignItems: "center", justifyContent: "space-between",
            }}>
              <div>
                <div style={{
                  fontFamily: "var(--font-heading)", fontSize: 17, fontWeight: 700,
                  color: "var(--tx-1)", letterSpacing: "-0.02em", marginBottom: 4,
                }}>
                  Klar til å bygge kupongen?
                </div>
                <div style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)" }}>
                  Optimaliser dekningsstrukturen ut fra ukens signaler og ditt budsjett.
                </div>
              </div>
              <Link
                href="/kupong"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  fontFamily: "var(--font-sans)", fontSize: 14, fontWeight: 600,
                  background: "var(--gold)", color: "#0a0a0b",
                  padding: "11px 22px", borderRadius: 10,
                  textDecoration: "none", flexShrink: 0,
                  transition: "opacity 0.15s ease",
                }}
              >
                Åpne kupong →
              </Link>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
