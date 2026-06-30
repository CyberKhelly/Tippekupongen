"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { getBets, getBetSummary, getBankroll, getInsights, generateBets, settleBets, scanAndGenerateBets, settleAllBets } from "@/lib/api";
import { deriveOddstips, type InsightItem, type MarketKey } from "@/lib/insights";
import type { PaperBet, BankrollPoint, BetSummary } from "@/lib/types";

const EASE = [0.16, 1, 0.3, 1] as const;

// ── Outcome labels ────────────────────────────────────────────────────────────

const OUTCOME_LABEL: Record<string, string> = {
  H: "Hjemme", U: "Uavgjort", B: "Borte",
  yes: "Begge scr.", no: "Ingen scr.", over: "Over 2.5", under: "Under 2.5",
};

const MARKET_LABEL: Record<string, string> = { "1x2": "1X2", btts: "BTTS", "over_2.5": "O2.5" };
const MARKET_COLOR: Record<string, string> = { "1x2": "#6098F2", btts: "#A78BFA", "over_2.5": "#F97316" };

type TimeRange = "1W" | "1M" | "3M" | "ALL";
type BetTab = "active" | "settled" | "signals";

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtNok(n: number, d = 0): string {
  return n.toLocaleString("nb-NO", { minimumFractionDigits: d, maximumFractionDigits: d }) + " kr";
}
function fmtPct(n: number | null, d = 1): string {
  return n == null ? "—" : `${n.toFixed(d)}%`;
}
function fmtPctSigned(n: number | null, d = 1): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(d)}%`;
}
function fmtOdds(n: number | null): string {
  return n == null ? "—" : n.toFixed(2);
}
function fmtEdge(n: number): string {
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n).toFixed(1)}pp`;
}

// ── Analytics helpers ─────────────────────────────────────────────────────────

function filterByRange(points: BankrollPoint[], range: TimeRange): BankrollPoint[] {
  if (range === "ALL" || points.length === 0) return points;
  const now = Date.now();
  const days = range === "1W" ? 7 : range === "1M" ? 30 : 90;
  const cutoff = now - days * 86_400_000;
  const filtered = points.filter(p => p.settled_at && new Date(p.settled_at).getTime() >= cutoff);
  return filtered.length > 0 ? [{ ...points[0], bankroll_after: filtered[0]?.bankroll_after ?? points[0].bankroll_after }, ...filtered] : points;
}

function computeMaxDrawdown(pts: BankrollPoint[]): number {
  let peak = -Infinity;
  let maxDD = 0;
  for (const p of pts) {
    if (p.bankroll_after > peak) peak = p.bankroll_after;
    if (peak > 0) {
      const dd = (peak - p.bankroll_after) / peak;
      if (dd > maxDD) maxDD = dd;
    }
  }
  return maxDD;
}

// ── Market chip ───────────────────────────────────────────────────────────────

function MarketChip({ market }: { market: string }) {
  const color = MARKET_COLOR[market] ?? "var(--tx-4)";
  return (
    <span style={{
      display: "inline-block", padding: "1px 7px", borderRadius: 4,
      fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
      color, background: `${color}20`,
    }}>
      {MARKET_LABEL[market] ?? market.toUpperCase()}
    </span>
  );
}

// ── Risk indicator ────────────────────────────────────────────────────────────

function RiskDot({ level }: { level: "low" | "medium" | "high" }) {
  const color = level === "low" ? "var(--green)" : level === "medium" ? "var(--gold)" : "var(--red)";
  const label = level === "low" ? "Lav" : level === "medium" ? "Middels" : "Høy";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <span style={{ width: 5, height: 5, borderRadius: "50%", background: color, flexShrink: 0 }} />
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)" }}>{label}</span>
    </span>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: PaperBet["status"] }) {
  const cfg = {
    pending: { label: "Avventer", color: "var(--tx-3)" },
    won:     { label: "Vunnet",  color: "var(--green)" },
    lost:    { label: "Tapt",    color: "var(--red)" },
    void:    { label: "Void",    color: "var(--tx-4)" },
  }[status];
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, color: cfg.color }}>
      {cfg.label}
    </span>
  );
}

// ── Bankroll hero chart ───────────────────────────────────────────────────────

function BankrollChart({ points, startBankroll }: { points: BankrollPoint[]; startBankroll: number }) {
  const W = 800, H = 200;
  const PL = 2, PR = 16, PT = 16, PB = 24;
  const svgRef = useRef<SVGPathElement>(null);
  const [drawn, setDrawn] = useState(false);

  const isUp = points.length > 1
    ? points[points.length - 1].bankroll_after >= startBankroll
    : true;
  const lineColor = isUp ? "var(--green)" : "var(--red)";

  const vals = points.map(p => p.bankroll_after);
  const allVals = [...vals, startBankroll];
  const minV = Math.min(...allVals) * 0.985;
  const maxV = Math.max(...allVals) * 1.015;
  const range = maxV - minV || 1;
  const n = points.length - 1;

  const toX = (i: number) => PL + (n > 0 ? (i / n) * (W - PL - PR) : W / 2);
  const toY = (v: number) => PT + (1 - (v - minV) / range) * (H - PT - PB);

  const pathPts = points.map((p, i) => `${toX(i).toFixed(1)},${toY(p.bankroll_after).toFixed(1)}`).join(" L ");
  const pathD = points.length > 0 ? `M ${pathPts}` : `M ${PL},${toY(startBankroll)} L ${W - PR},${toY(startBankroll)}`;
  const lastX = points.length > 0 ? toX(points.length - 1) : W - PR;
  const lastY = points.length > 0 ? toY(points[points.length - 1].bankroll_after) : toY(startBankroll);
  const baseY = toY(startBankroll);

  const fillD = points.length > 0
    ? `M ${toX(0).toFixed(1)},${H - PB} L ${pathPts} L ${lastX.toFixed(1)},${H - PB} Z`
    : `M ${PL},${H - PB} L ${W - PR},${H - PB} Z`;

  // Y-axis guide values
  const guides = [0.25, 0.5, 0.75].map(t => minV + t * range);

  useEffect(() => {
    if (!svgRef.current) return;
    const length = svgRef.current.getTotalLength?.() ?? 2000;
    svgRef.current.style.strokeDasharray = `${length}`;
    svgRef.current.style.strokeDashoffset = `${length}`;
    const t = setTimeout(() => {
      if (svgRef.current) {
        svgRef.current.style.transition = "stroke-dashoffset 1.6s cubic-bezier(0.16,1,0.3,1)";
        svgRef.current.style.strokeDashoffset = "0";
        setDrawn(true);
      }
    }, 100);
    return () => clearTimeout(t);
  }, [points.length]);

  const gradId = isUp ? "greenGrad" : "redGrad";
  const fillColor = isUp ? "rgba(95,174,110," : "rgba(200,85,78,";

  return (
    <div style={{ position: "relative", width: "100%" }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        width="100%"
        height={220}
        style={{ display: "block" }}
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={fillColor + "0.15)"} />
            <stop offset="100%" stopColor={fillColor + "0.01)"} />
          </linearGradient>
        </defs>

        {/* Guide lines */}
        {guides.map((v, i) => (
          <line key={i}
            x1={PL} y1={toY(v)} x2={W - PR} y2={toY(v)}
            stroke="rgba(255,255,255,0.04)" strokeWidth="0.7"
          />
        ))}

        {/* Baseline (starting bankroll) */}
        <line
          x1={PL} y1={baseY} x2={W - PR} y2={baseY}
          stroke="rgba(255,255,255,0.14)" strokeWidth="0.8" strokeDasharray="4 5"
        />

        {/* Fill area */}
        <path d={fillD} fill={`url(#${gradId})`} />

        {/* Line */}
        <path ref={svgRef} d={pathD} fill="none" stroke={lineColor} strokeWidth="1.8"
              strokeLinejoin="round" strokeLinecap="round" />

        {/* End dot */}
        {points.length > 0 && (
          <>
            <circle cx={lastX} cy={lastY} r="3.5" fill={lineColor} />
            <circle cx={lastX} cy={lastY} r="6" fill={lineColor} fillOpacity={0.22} />
          </>
        )}

        {/* Y-axis labels */}
        {guides.map((v, i) => (
          <text key={i} x={W - PR + 3} y={toY(v) + 3.5}
            fontFamily="var(--font-mono)" fontSize="8" fill="rgba(255,255,255,0.25)"
            textAnchor="start">
            {(v / 1000).toFixed(0)}k
          </text>
        ))}
      </svg>
    </div>
  );
}

// ── Metric tile ───────────────────────────────────────────────────────────────

function MetricTile({ label, value, sub, valueColor, wide = false }: {
  label: string; value: string; sub?: string; valueColor?: string; wide?: boolean;
}) {
  return (
    <div style={{
      padding: "16px 20px",
      background: "var(--surf-1)",
      border: "1px solid rgba(255,255,255,0.07)",
      borderRadius: 12, flex: wide ? "1.5" : "1", minWidth: 0,
    }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 8 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 800, color: valueColor ?? "var(--tx-1)", letterSpacing: "-0.04em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", marginTop: 5 }}>{sub}</div>
      )}
    </div>
  );
}

// ── Bet row (expanded) ────────────────────────────────────────────────────────

function ExpandedBetDetail({ bet }: { bet: PaperBet }) {
  const qc = useQueryClient();
  const settleMutation = useMutation({
    mutationFn: () => settleBets(bet.fixture_id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] });
      qc.invalidateQueries({ queryKey: ["bet-summary"] });
      qc.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });
  const isPastKickoff = bet.kickoff_utc != null && new Date(bet.kickoff_utc) < new Date();

  return (
    <div style={{
      padding: "14px 24px 16px",
      background: "#0C0C0F",
      borderTop: "1px solid rgba(255,255,255,0.06)",
    }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 20 }}>
        {/* Probability comparison */}
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
            SANNSYNLIGHET
          </div>
          {[
            { label: "MODELL", pct: bet.model_prob * 100, color: "var(--gold)" },
            { label: "MARKED", pct: bet.implied_prob * 100, color: "var(--tx-3)" },
          ].map(({ label, pct, color }) => (
            <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", width: 46, flexShrink: 0 }}>{label}</span>
              <div style={{ flex: 1, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden", position: "relative" }}>
                <div style={{ position: "absolute", inset: 0, background: color, borderRadius: 2, transform: `scaleX(${Math.min(pct, 100) / 100})`, transformOrigin: "left", transition: "transform 0.6s ease" }} />
              </div>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, color, width: 36, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                {fmtPct(pct)}
              </span>
            </div>
          ))}
        </div>

        {/* Bet details */}
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
            SPILL-DETALJER
          </div>
          {[
            { k: "Bookmaker", v: bet.bookmaker },
            { k: "Innsats", v: fmtNok(bet.stake_nok) },
            { k: "EV", v: fmtNok(bet.expected_value) },
            bet.kickoff_utc ? { k: "Avspark", v: new Date(bet.kickoff_utc).toLocaleString("nb-NO", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) } : null,
          ].filter(Boolean).map(item => (
            <div key={item!.k} style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>{item!.k}</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-2)", fontVariantNumeric: "tabular-nums" }}>{item!.v}</span>
            </div>
          ))}
        </div>

        {/* Result / CLV */}
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>
            RESULTAT
          </div>
          {bet.status === "pending" && isPastKickoff ? (
            <button
              onClick={() => settleMutation.mutate()}
              disabled={settleMutation.isPending}
              style={{
                padding: "6px 14px", borderRadius: 6, border: "1px solid rgba(201,160,74,0.4)",
                background: "rgba(201,160,74,0.10)", color: "var(--gold)",
                fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700,
                letterSpacing: "0.08em", cursor: "pointer",
                opacity: settleMutation.isPending ? 0.5 : 1,
              }}
            >
              {settleMutation.isPending ? "..." : "GJØR OPP"}
            </button>
          ) : bet.status !== "pending" && (
            <div style={{ marginBottom: 8 }}>
              <StatusBadge status={bet.status} />
              {bet.profit_nok !== null && (
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 800,
                  color: bet.profit_nok >= 0 ? "var(--green)" : "var(--red)",
                  marginTop: 4, fontVariantNumeric: "tabular-nums",
                }}>
                  {bet.profit_nok >= 0 ? "+" : ""}{fmtNok(bet.profit_nok)}
                </div>
              )}
            </div>
          )}
          {bet.clv !== null && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", marginBottom: 3 }}>CLV</div>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700,
                color: (bet.clv ?? 0) >= 0 ? "var(--gold)" : "var(--red)",
                fontVariantNumeric: "tabular-nums",
              }}>
                {(bet.clv ?? 0) >= 0 ? "+" : ""}{((bet.clv ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
          )}
          {bet.reason && (
            <p style={{
              fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--tx-3)",
              margin: "10px 0 0", lineHeight: 1.5,
            }}>
              {bet.reason}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Bet table row ─────────────────────────────────────────────────────────────

function BetRow({ bet, isLast, delay }: { bet: PaperBet; isLast: boolean; delay: number }) {
  const [expanded, setExpanded] = useState(false);
  const isPos = bet.edge_pp > 0;
  const plColor = bet.profit_nok === null ? "var(--tx-3)"
    : bet.profit_nok >= 0 ? "var(--green)" : "var(--red)";

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.25, ease: EASE }}
    >
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: "100%", textAlign: "left", border: "none", cursor: "pointer",
          display: "grid",
          gridTemplateColumns: "1fr 56px 72px 56px 58px 58px 64px 60px 68px 24px",
          padding: "13px 20px", gap: 8, alignItems: "center",
          background: expanded ? "#0C0C0F" : "transparent",
          borderBottom: !isLast || expanded ? "1px solid rgba(255,255,255,0.05)" : "none",
          transition: "background 0.12s",
        }}
      >
        {/* Match */}
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontFamily: "var(--font-heading)", fontSize: 13, fontWeight: 600,
            color: "var(--tx-1)", letterSpacing: "-0.015em",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {bet.match_name}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 2 }}>
            {bet.league && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
                {bet.league}
              </span>
            )}
            {!bet.coupon_id && (
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.06em",
                color: "var(--green)", background: "rgba(95,174,110,0.12)",
                borderRadius: 3, padding: "1px 4px",
              }}>SCAN</span>
            )}
            {bet.insight_type?.startsWith("tier_") && (() => {
              const tier = bet.insight_type.replace("tier_", "").toUpperCase();
              const cfg: Record<string, { bg: string; color: string }> = {
                A: { bg: "rgba(95,174,110,0.15)", color: "var(--green)" },
                B: { bg: "rgba(201,160,74,0.13)", color: "var(--gold)" },
                C: { bg: "rgba(255,255,255,0.06)", color: "var(--tx-3)" },
              };
              const c = cfg[tier] ?? cfg["C"];
              return (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.04em",
                  color: c.color, background: c.bg, borderRadius: 3, padding: "1px 5px",
                }}>
                  Tier {tier}
                </span>
              );
            })()}
            {bet.model_quality && (() => {
              const qCfg: Record<string, { label: string; color: string; bg: string }> = {
                full_model:    { label: "Full modell",    color: "var(--green)",  bg: "rgba(95,174,110,0.12)" },
                partial_model: { label: "Delvis modell",  color: "var(--green)",  bg: "rgba(95,174,110,0.09)" },
                af_supported:  { label: "AF-støttet",     color: "var(--gold)",   bg: "rgba(201,160,74,0.13)" },
                generic_prior: { label: "Eurosnitt-prior",color: "var(--tx-3)",   bg: "rgba(255,255,255,0.05)" },
              };
              const q = qCfg[bet.model_quality];
              if (!q) return null;
              return (
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.04em",
                  color: q.color, background: q.bg, borderRadius: 3, padding: "1px 5px",
                }}>
                  {q.label}
                </span>
              );
            })()}
          </div>
        </div>

        {/* Market */}
        <div><MarketChip market={bet.market} /></div>

        {/* Pick */}
        <div style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-2)" }}>
          {OUTCOME_LABEL[bet.outcome] ?? bet.outcome}
        </div>

        {/* Odds */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--tx-1)", fontVariantNumeric: "tabular-nums" }}>
          {fmtOdds(bet.ref_odds)}
        </div>

        {/* Model % */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--gold)", fontVariantNumeric: "tabular-nums" }}>
          {fmtPct(bet.model_prob * 100)}
        </div>

        {/* Market % */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--tx-3)", fontVariantNumeric: "tabular-nums" }}>
          {fmtPct(bet.implied_prob * 100)}
        </div>

        {/* Edge */}
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700,
          color: isPos ? "var(--gold)" : "var(--indigo)",
          fontVariantNumeric: "tabular-nums",
        }}>
          {fmtEdge(bet.edge_pp)}
        </div>

        {/* Stake */}
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--tx-2)", fontVariantNumeric: "tabular-nums" }}>
          {bet.stake_nok} kr
        </div>

        {/* Risk */}
        <div><RiskDot level={bet.risk_level} /></div>

        {/* Expand */}
        <div style={{ color: "var(--tx-4)", fontSize: 10, textAlign: "center" }}>
          {expanded ? "▲" : "▼"}
        </div>
      </button>

      <div style={{ display: "grid", gridTemplateRows: expanded ? "1fr" : "0fr", transition: "grid-template-rows 0.2s ease" }}>
        <div style={{ overflow: "hidden" }}>
          <ExpandedBetDetail bet={bet} />
        </div>
      </div>
    </motion.div>
  );
}

// ── Signal row (from insights, no paper bet yet) ──────────────────────────────

function SignalRow({ item, isLast, delay }: { item: InsightItem; isLast: boolean; delay: number }) {
  const [expanded, setExpanded] = useState(false);
  const isPos = item.marketEdgePp > 0;
  const modelPct = item.modelProb;
  const impliedPct = item.impliedProb;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.25, ease: EASE }}
    >
      <button
        onClick={() => setExpanded(e => !e)}
        style={{
          width: "100%", textAlign: "left", border: "none", cursor: "pointer",
          display: "grid",
          gridTemplateColumns: "1fr 56px 72px 56px 58px 58px 64px 60px 68px 24px",
          padding: "13px 20px", gap: 8, alignItems: "center",
          background: expanded ? "#0C0C0F" : "transparent",
          borderBottom: !isLast || expanded ? "1px solid rgba(255,255,255,0.05)" : "none",
          transition: "background 0.12s",
        }}
      >
        <div style={{ minWidth: 0 }}>
          <div style={{
            fontFamily: "var(--font-heading)", fontSize: 13, fontWeight: 600,
            color: "var(--tx-1)", letterSpacing: "-0.015em",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {item.signal.home_team} – {item.signal.away_team}
          </div>
          {item.signal.league_name && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", marginTop: 2 }}>
              {item.signal.league_name}
            </div>
          )}
        </div>
        <div><MarketChip market={item.market} /></div>
        <div style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-2)" }}>{item.pickLabel}</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--tx-1)", fontVariantNumeric: "tabular-nums" }}>
          {fmtOdds(item.refOdds)}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--gold)", fontVariantNumeric: "tabular-nums" }}>
          {fmtPct(modelPct)}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--tx-3)", fontVariantNumeric: "tabular-nums" }}>
          {fmtPct(impliedPct)}
        </div>
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700,
          color: isPos ? "var(--gold)" : "var(--indigo)", fontVariantNumeric: "tabular-nums",
        }}>
          {fmtEdge(item.marketEdgePp)}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--tx-4)" }}>—</div>
        <div><RiskDot level={item.riskLevel} /></div>
        <div style={{ color: "var(--tx-4)", fontSize: 10, textAlign: "center" }}>
          {expanded ? "▲" : "▼"}
        </div>
      </button>
      <div style={{ display: "grid", gridTemplateRows: expanded ? "1fr" : "0fr", transition: "grid-template-rows 0.2s ease" }}>
        <div style={{ overflow: "hidden" }}>
          <div style={{ padding: "14px 20px 16px", background: "#0C0C0F", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, maxWidth: 560 }}>
              <div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>SANNSYNLIGHET</div>
                {[
                  { label: "MODELL", pct: modelPct, color: "var(--gold)" },
                  { label: "MARKED", pct: impliedPct, color: "var(--tx-3)" },
                ].map(({ label, pct, color }) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)", width: 46, flexShrink: 0 }}>{label}</span>
                    <div style={{ flex: 1, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)", overflow: "hidden", position: "relative" }}>
                      <div style={{ position: "absolute", inset: 0, background: color, borderRadius: 2, transform: `scaleX(${Math.min(pct, 100) / 100})`, transformOrigin: "left" }} />
                    </div>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, color, width: 36, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {fmtPct(pct)}
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 10 }}>ANALYSE</div>
                <p style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-3)", lineHeight: 1.55, margin: 0 }}>
                  {item.explanation}
                </p>
                {item.bookmaker && (
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", marginTop: 6 }}>
                    {item.bookmaker}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

// ── Column headers ────────────────────────────────────────────────────────────

function ColHeaders() {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr 56px 72px 56px 58px 58px 64px 60px 68px 24px",
      padding: "8px 20px",
      background: "rgba(255,255,255,0.02)",
      borderBottom: "1px solid rgba(255,255,255,0.06)",
      gap: 8,
    }}>
      {["KAMP", "MARKED", "VALG", "ODDS", "MODELL", "BK. PROB", "KANT", "INNSATS", "RISIKO", ""].map((h, i) => (
        <span key={i} style={{
          fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 600,
          letterSpacing: "0.10em", color: "var(--tx-4)",
        }}>{h}</span>
      ))}
    </div>
  );
}

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({ weekLabel }: { weekLabel: string }) {
  return (
    <header style={{
      position: "sticky", top: 0, zIndex: 20,
      background: "var(--surf-0)", borderBottom: "1px solid rgba(255,255,255,0.06)",
      height: 44, display: "flex", alignItems: "center", padding: "0 40px", gap: 14,
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: "var(--gold)" }}>
        ODDS-INTELLIGENS
      </span>
      <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.10)" }} />
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
        Modell vs. bokmekermarked
      </span>
      {weekLabel && (
        <>
          <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.10)" }} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
            {weekLabel}
          </span>
        </>
      )}
    </header>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ModellspillPage() {
  const qc = useQueryClient();
  const [timeRange, setTimeRange] = useState<TimeRange>("ALL");
  const [betTab, setBetTab] = useState<BetTab>("active");

  const { data: bets = [], isLoading: loadingBets } = useQuery({
    queryKey: ["bets"],
    queryFn: () => getBets(),
    staleTime: 30_000,
  });

  const { data: summary } = useQuery({
    queryKey: ["bet-summary"],
    queryFn: getBetSummary,
    staleTime: 30_000,
  });

  const { data: bankrollPts = [] } = useQuery({
    queryKey: ["bankroll"],
    queryFn: getBankroll,
    staleTime: 30_000,
  });

  const { data: insights } = useQuery({
    queryKey: ["insights"],
    queryFn: () => getInsights(),
    staleTime: 60_000,
    refetchInterval: 120_000,
  });

  const generateMutation = useMutation({
    mutationFn: () => generateBets(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] });
      qc.invalidateQueries({ queryKey: ["bet-summary"] });
      qc.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });

  const scanMutation = useMutation({
    mutationFn: () => scanAndGenerateBets(72),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] });
      qc.invalidateQueries({ queryKey: ["bet-summary"] });
      qc.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });

  const settleAllMutation = useMutation({
    mutationFn: () => settleAllBets(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["bets"] });
      qc.invalidateQueries({ queryKey: ["bet-summary"] });
      qc.invalidateQueries({ queryKey: ["bankroll"] });
    },
  });

  const startBankroll = summary?.starting_bankroll ?? 10_000;
  const filteredPts   = useMemo(() => filterByRange(bankrollPts, timeRange), [bankrollPts, timeRange]);

  const active  = useMemo(() => bets.filter(b => b.status === "pending"), [bets]);
  const settled = useMemo(() => bets.filter(b => b.status !== "pending" && b.status !== "void"), [bets]);

  const signals = useMemo(() => {
    if (!insights?.signals) return [];
    return deriveOddstips(insights.signals).allItems.sort((a, b) => b.marketEdgePp - a.marketEdgePp);
  }, [insights]);

  const weekLabel = insights ? `UKE ${insights.week}/${insights.year}` : "";

  const currentBankroll = summary?.current_bankroll ?? startBankroll;
  const totalProfit     = summary?.total_profit ?? 0;
  const roi             = summary?.roi ?? null;
  const hitRate         = summary?.hit_rate ?? null;
  const nSettled        = settled.length;
  const avgOdds         = nSettled > 0
    ? settled.reduce((s, b) => s + b.ref_odds, 0) / nSettled
    : null;
  const maxDrawdown     = computeMaxDrawdown(bankrollPts);

  const isUp = totalProfit >= 0;
  const plColor = isUp ? "var(--green)" : "var(--red)";

  return (
    <div className="min-h-screen" style={{ marginLeft: 240, background: "var(--canvas)" }}>
      <TopBar weekLabel={weekLabel} />

      <main style={{ maxWidth: 1180, margin: "0 auto", padding: "0 0 72px" }}>

        {/* ── HERO: Bankroll chart ── */}
        <div style={{
          background: "var(--surf-1)",
          borderBottom: "1px solid rgba(255,255,255,0.07)",
          padding: "32px 40px 24px",
        }}>
          {/* Big number + controls */}
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 20 }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 8 }}>
                BANKROLL
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 38, fontWeight: 800,
                  color: "var(--tx-1)", letterSpacing: "-0.05em", lineHeight: 1,
                  fontVariantNumeric: "tabular-nums",
                }}>
                  {fmtNok(currentBankroll)}
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 700,
                  color: plColor, letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums",
                }}>
                  {totalProfit >= 0 ? "+" : ""}{fmtNok(totalProfit)}
                </span>
                {roi !== null && (
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600,
                    color: plColor, opacity: 0.8, fontVariantNumeric: "tabular-nums",
                  }}>
                    ({fmtPctSigned(roi, 1)})
                  </span>
                )}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", marginTop: 8 }}>
                Startkapital {fmtNok(startBankroll)} · {nSettled} avgjorte spill
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, flexShrink: 0 }}>
              {/* Time range tabs */}
              <div style={{ display: "flex", gap: 2, padding: "3px", background: "rgba(255,255,255,0.04)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.07)" }}>
                {(["1W", "1M", "3M", "ALL"] as TimeRange[]).map(r => (
                  <button key={r} onClick={() => setTimeRange(r)} style={{
                    padding: "5px 11px", borderRadius: 6, border: "none", cursor: "pointer",
                    background: timeRange === r ? "rgba(255,255,255,0.08)" : "transparent",
                    fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: timeRange === r ? 700 : 400,
                    color: timeRange === r ? "var(--tx-1)" : "var(--tx-4)",
                    transition: "all 0.12s",
                  }}>{r}</button>
                ))}
              </div>

              {/* Settle all — fetch results + settle expired bets */}
              <button
                onClick={() => settleAllMutation.mutate()}
                disabled={settleAllMutation.isPending}
                title="Hent resultater fra API-Football og gjør opp utløpte spill"
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", borderRadius: 8,
                  border: "1px solid rgba(123,146,255,0.25)",
                  background: "rgba(123,146,255,0.07)",
                  color: "var(--indigo)",
                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, cursor: "pointer",
                  opacity: settleAllMutation.isPending ? 0.5 : 1,
                  transition: "opacity 0.15s", whiteSpace: "nowrap",
                }}
              >
                {settleAllMutation.isPending ? "Henter…" : "Gjør opp alle"}
              </button>

              {/* Scan button — global league scan, not coupon-limited */}
              <button
                onClick={() => scanMutation.mutate()}
                disabled={scanMutation.isPending || generateMutation.isPending}
                title="Scanner alle tilgjengelige kamper — ikke bare Tippekupongen"
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", borderRadius: 8,
                  border: "1px solid rgba(95,174,110,0.25)",
                  background: "rgba(95,174,110,0.07)",
                  color: "var(--green)",
                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, cursor: "pointer",
                  opacity: scanMutation.isPending ? 0.5 : 1,
                  transition: "opacity 0.15s", whiteSpace: "nowrap",
                }}
              >
                {scanMutation.isPending ? "Scanner…" : "Scan alle kamper"}
              </button>

              {/* Generate button — coupon-scoped */}
              <button
                onClick={() => generateMutation.mutate()}
                disabled={generateMutation.isPending || scanMutation.isPending}
                style={{
                  display: "flex", alignItems: "center", gap: 6,
                  padding: "8px 14px", borderRadius: 8,
                  border: "1px solid rgba(201,160,74,0.25)",
                  background: "rgba(201,160,74,0.08)",
                  color: "var(--gold)",
                  fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, cursor: "pointer",
                  opacity: generateMutation.isPending ? 0.5 : 1,
                  transition: "opacity 0.15s", whiteSpace: "nowrap",
                }}
              >
                {generateMutation.isPending ? "..." : "Generer (kupong)"}
              </button>
            </div>
          </div>

          {/* Chart */}
          <BankrollChart points={filteredPts} startBankroll={startBankroll} />

          {/* Chart baseline label */}
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
              Start {fmtNok(startBankroll)} ·····
            </span>
            {filteredPts.length > 1 && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
                {filteredPts[filteredPts.length - 1]?.settled_at
                  ? new Date(filteredPts[filteredPts.length - 1].settled_at!).toLocaleDateString("nb-NO")
                  : ""}
              </span>
            )}
          </div>
        </div>

        {/* ── Metrics row ── */}
        <div style={{ padding: "20px 40px", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
          <div style={{ display: "flex", gap: 10 }}>
            <MetricTile label="ROI" value={roi !== null ? fmtPctSigned(roi) : "—"} valueColor={roi !== null ? (roi >= 0 ? "var(--green)" : "var(--red)") : "var(--tx-3)"} sub="avkastning" />
            <MetricTile label="TREFFRATE" value={hitRate !== null ? fmtPct(hitRate) : "—"} sub={`${summary?.n_won ?? 0}/${nSettled} vunnet`} />
            <MetricTile label="SNITT ODDS" value={avgOdds !== null ? avgOdds.toFixed(2) : "—"} sub="per spill" />
            <MetricTile label="SPILL" value={String(nSettled + active.length)} sub={`${active.length} aktive · ${nSettled} avgjorte`} />
            <MetricTile label="MAKS DRAWDOWN" value={maxDrawdown > 0 ? `${(maxDrawdown * 100).toFixed(1)}%` : "—"} valueColor={maxDrawdown > 0.15 ? "var(--red)" : "var(--tx-1)"} sub="fra topp" />
            <MetricTile label="SNITT CLV" value={summary?.avg_clv !== null && summary?.avg_clv !== undefined ? `${(summary.avg_clv >= 0 ? "+" : "")}${summary.avg_clv.toFixed(1)}%` : "—"} valueColor="var(--gold)" sub="closing line value" />
          </div>
        </div>

        {/* ── Scan / generate result banners ── */}
        {scanMutation.isSuccess && (() => {
          const d = scanMutation.data;
          const c = d.candidates;
          const tiers = c.tiers;
          const rej = c.rejection_breakdown;
          return (
            <div style={{
              margin: "12px 40px 0", padding: "12px 16px", borderRadius: 8,
              fontFamily: "var(--font-mono)", fontSize: 10,
              background: "rgba(95,174,110,0.06)", border: "1px solid rgba(95,174,110,0.18)",
            }}>
              {/* Row 1: scan summary */}
              <div style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 8, color: "var(--green)" }}>
                <span>Skannet {d.scan.n_leagues} ligaer · {d.scan.n_fixtures_found} kamper · {d.scan.n_fixtures_new} nye</span>
                <span style={{ color: "var(--tx-4)" }}>{d.duration_s}s · {d.scan.n_api_calls} API-kall</span>
              </div>
              {/* Row 2: tier breakdown */}
              <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
                <span style={{ color: c.n_created > 0 ? "var(--gold)" : "var(--tx-4)" }}>
                  {c.n_created > 0 ? `${c.n_created} nye kandidater` : "Ingen nye kandidater"}
                </span>
                {c.n_created > 0 && (
                  <>
                    <span style={{ color: "#F4F3F0", background: "rgba(95,174,110,0.15)", borderRadius: 4, padding: "1px 7px" }}>A:{tiers.a}</span>
                    <span style={{ color: "#F4F3F0", background: "rgba(201,160,74,0.12)", borderRadius: 4, padding: "1px 7px" }}>B:{tiers.b}</span>
                    <span style={{ color: "#F4F3F0", background: "rgba(255,255,255,0.06)", borderRadius: 4, padding: "1px 7px" }}>C:{tiers.c}</span>
                  </>
                )}
                <span style={{ color: "var(--tx-4)", marginLeft: 8 }}>
                  Forkastet: {rej.edge_too_small} under {c.min_edge_pp}pp
                  {rej.no_enr_1x2 > 0 && ` · ${rej.no_enr_1x2} 1X2 uten data`}
                  {rej.duplicate > 0 && ` · ${rej.duplicate} duplikat`}
                  {rej.error > 0 && ` · ${rej.error} feil`}
                </span>
              </div>
            </div>
          );
        })()}
        {generateMutation.isSuccess && (
          <div style={{
            margin: "12px 40px 0", padding: "10px 16px", borderRadius: 8,
            fontFamily: "var(--font-mono)", fontSize: 10,
            color: "var(--green)", background: "rgba(95,174,110,0.08)", border: "1px solid rgba(95,174,110,0.20)",
          }}>
            {(generateMutation.data as any).created > 0
              ? `${(generateMutation.data as any).created} nye spill generert fra kupong.`
              : "Ingen nye kupong-spill — alle er allerede registrert."}
          </div>
        )}
        {settleAllMutation.isSuccess && (() => {
          const d = settleAllMutation.data;
          return (
            <div style={{
              margin: "12px 40px 0", padding: "10px 16px", borderRadius: 8,
              fontFamily: "var(--font-mono)", fontSize: 10,
              background: "rgba(123,146,255,0.06)", border: "1px solid rgba(123,146,255,0.18)",
            }}>
              <div style={{ display: "flex", gap: 20, flexWrap: "wrap", color: "var(--indigo)" }}>
                {d.settled === 0
                  ? <span>Ingen utløpte spill å gjøre opp.</span>
                  : <span>Gjort opp {d.settled} spill — {d.won} vunnet · {d.lost} tapt · {d.profit_nok >= 0 ? "+" : ""}{d.profit_nok.toLocaleString("nb-NO")} kr P/L</span>
                }
                {d.results_fetched > 0 && (
                  <span style={{ color: "var(--tx-4)" }}>{d.results_fetched} resultat{d.results_fetched !== 1 ? "er" : ""} hentet</span>
                )}
                {d.fetch_errors > 0 && (
                  <span style={{ color: "var(--tx-4)" }}>{d.fetch_errors} feil ved henting</span>
                )}
              </div>
            </div>
          );
        })()}

        {/* ── Bet section ── */}
        <div style={{ padding: "28px 40px 0" }}>
          {/* Scope label */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
            <span style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.08em",
              color: "var(--green)", background: "rgba(95,174,110,0.10)",
              border: "1px solid rgba(95,174,110,0.18)", borderRadius: 5,
              padding: "3px 8px",
            }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "var(--green)", display: "inline-block" }} />
              ODDS-INTELLIGENS
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
              Scanner alle tilgjengelige kamper — ikke bare Tippekupongen
            </span>
          </div>

          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 2, marginBottom: 16, borderBottom: "1px solid rgba(255,255,255,0.07)", paddingBottom: 0 }}>
            {([
              { key: "active",   label: "Aktive",       count: active.length },
              { key: "settled",  label: "Avgjorte",     count: settled.length },
              { key: "signals",  label: "Signaler",     count: signals.length },
            ] as { key: BetTab; label: string; count: number }[]).map(({ key, label, count }) => (
              <button key={key} onClick={() => setBetTab(key)} style={{
                padding: "10px 16px",
                border: "none", cursor: "pointer",
                background: "transparent",
                borderBottom: `2px solid ${betTab === key ? "var(--gold)" : "transparent"}`,
                fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: betTab === key ? 700 : 400,
                color: betTab === key ? "var(--tx-1)" : "var(--tx-4)",
                transition: "all 0.12s",
                display: "flex", alignItems: "center", gap: 7,
              }}>
                {label}
                {count > 0 && (
                  <span style={{
                    fontFamily: "var(--font-mono)", fontSize: 9,
                    background: betTab === key ? "rgba(201,160,74,0.14)" : "rgba(255,255,255,0.06)",
                    color: betTab === key ? "var(--gold)" : "var(--tx-4)",
                    borderRadius: 5, padding: "1px 6px",
                  }}>{count}</span>
                )}
              </button>
            ))}
          </div>

          {/* Table */}
          <div style={{
            border: "1px solid rgba(255,255,255,0.07)",
            borderRadius: 12, overflow: "hidden",
          }}>
            <ColHeaders />

            {/* Active bets */}
            {betTab === "active" && (
              loadingBets ? (
                <div style={{ padding: "40px 0", textAlign: "center" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--tx-4)" }}>Laster spill…</span>
                </div>
              ) : active.length === 0 ? (
                <div style={{ padding: "48px 40px", textAlign: "center" }}>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--tx-3)", marginBottom: 8 }}>
                    Ingen aktive spill
                  </div>
                  <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                    Klikk «Generer spill» for å opprette papirspill fra ukens signaler.
                  </div>
                </div>
              ) : active.map((bet, i) => (
                <BetRow key={bet.id} bet={bet} isLast={i === active.length - 1} delay={i * 0.03} />
              ))
            )}

            {/* Settled bets */}
            {betTab === "settled" && (
              settled.length === 0 ? (
                <div style={{ padding: "48px 40px", textAlign: "center" }}>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--tx-3)", marginBottom: 8 }}>
                    Ingen avgjorte spill ennå
                  </div>
                  <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                    Avgjorte spill vises her etter at kamper er spilt.
                  </div>
                </div>
              ) : settled.map((bet, i) => (
                <BetRow key={bet.id} bet={bet} isLast={i === settled.length - 1} delay={i * 0.03} />
              ))
            )}

            {/* Signals */}
            {betTab === "signals" && (
              signals.length === 0 ? (
                <div style={{ padding: "48px 40px", textAlign: "center" }}>
                  <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--tx-3)", marginBottom: 8 }}>
                    Ingen signaler over terskelen
                  </div>
                  <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                    Signaler med modellkant mot bokmaker vises her etter synkronisering.
                  </div>
                </div>
              ) : signals.map((item, i) => (
                <SignalRow key={`${item.signal.fixture_id}-${item.market}`} item={item} isLast={i === signals.length - 1} delay={i * 0.03} />
              ))
            )}
          </div>

          {/* Footnote */}
          <div style={{
            marginTop: 16, padding: "10px 14px", borderRadius: 8,
            background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)",
          }}>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 11, color: "var(--tx-4)", margin: 0, lineHeight: 1.6 }}>
              <strong style={{ color: "var(--tx-3)" }}>Om Modellspill:</strong> Kant = modellsannsynlighet − implisert sannsynlighet (de-vigget fra bookmaker-odds). NT folkeprosenter brukes aldri i modellen. Odds er fra tilgjengelige bookmaker-markeder (API-Football/Bet365) — ingen ekte penger er involvert.
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
