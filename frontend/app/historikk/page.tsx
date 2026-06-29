"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  getHistory, getHistoryStrategyPerformance, getHistoryNtComparison,
  getStrategyAnalytics, getBetSummary, getBankroll,
} from "@/lib/api";
import type {
  HistoryCouponItem, StrategyPerformance, GenerationAnalytics,
  BetSummary, BankrollPoint,
} from "@/lib/types";

const EASE = [0.16, 1, 0.3, 1] as const;

// ── Animated counter ──────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1400, delay = 0): number {
  const [val, setVal] = useState(0);
  useEffect(() => {
    if (target === 0) { setVal(0); return; }
    let raf: number;
    const t0 = performance.now() + delay;
    const tick = (now: number) => {
      const t = Math.min(Math.max((now - t0) / duration, 0), 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setVal(target * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, delay]);
  return val;
}

// ── Mode toggle ───────────────────────────────────────────────────────────────

type Mode = "kupong" | "odds";

function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (m: Mode) => void }) {
  return (
    <div style={{ display: "flex", gap: 2, padding: "3px", background: "rgba(255,255,255,0.04)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.07)" }}>
      {(["kupong", "odds"] as Mode[]).map(m => (
        <button key={m} onClick={() => onChange(m)} style={{
          padding: "8px 20px", borderRadius: 8, border: "none", cursor: "pointer",
          background: mode === m ? "rgba(201,160,74,0.12)" : "transparent",
          fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: mode === m ? 700 : 400,
          color: mode === m ? "var(--gold)" : "var(--tx-4)",
          transition: "all 0.15s",
        }}>
          {m === "kupong" ? "Kupong-historikk" : "Odds-historikk"}
        </button>
      ))}
    </div>
  );
}

// ── Animated hero counter tile ────────────────────────────────────────────────

function HeroTile({ label, raw, formatted, sub, color, delay = 0, huge = false }: {
  label: string; raw: number; formatted: (v: number) => string; sub?: string;
  color?: string; delay?: number; huge?: boolean;
}) {
  const val = useCountUp(raw, 1200, delay);
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: delay / 1000, ease: EASE }}
      style={{ flex: 1, minWidth: 0 }}
    >
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.14em", color: "var(--tx-4)", marginBottom: 10 }}>
        {label}
      </div>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: huge ? 46 : 36, fontWeight: 800,
        color: color ?? "var(--tx-1)", letterSpacing: "-0.05em", lineHeight: 1,
        fontVariantNumeric: "tabular-nums",
      }}>
        {formatted(val)}
      </div>
      {sub && (
        <div style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-4)", marginTop: 8, lineHeight: 1.4 }}>
          {sub}
        </div>
      )}
    </motion.div>
  );
}

// ── Dual-line SVG chart ───────────────────────────────────────────────────────

interface ChartPoint { x: number; y: number; label?: string }

function DualLineChart({ series1, series2, baseline, label1, label2, yFmt }: {
  series1: ChartPoint[]; series2: ChartPoint[];
  baseline?: number;
  label1: string; label2: string;
  yFmt?: (v: number) => string;
}) {
  const lineRef = useRef<SVGPathElement>(null);
  const W = 800, H = 220, PL = 48, PR = 24, PT = 16, PB = 32;

  useEffect(() => {
    if (!lineRef.current) return;
    const len = lineRef.current.getTotalLength?.() ?? 2000;
    lineRef.current.style.strokeDasharray = `${len}`;
    lineRef.current.style.strokeDashoffset = `${len}`;
    const t = setTimeout(() => {
      if (lineRef.current) {
        lineRef.current.style.transition = "stroke-dashoffset 1.8s cubic-bezier(0.16,1,0.3,1)";
        lineRef.current.style.strokeDashoffset = "0";
      }
    }, 200);
    return () => clearTimeout(t);
  }, [series1.length]);

  const allY = [
    ...series1.map(p => p.y),
    ...series2.map(p => p.y),
    ...(baseline !== undefined ? [baseline] : []),
  ];
  if (allY.length === 0) return null;

  const minY = Math.min(...allY) * (Math.min(...allY) < 0 ? 1.08 : 0.92);
  const maxY = Math.max(...allY) * 1.08;
  const rangeY = maxY - minY || 1;

  const allX = [...series1.map(p => p.x), ...series2.map(p => p.x)];
  const minX = Math.min(...allX);
  const maxX = Math.max(...allX);
  const rangeX = maxX - minX || 1;

  const tx = (x: number) => PL + ((x - minX) / rangeX) * (W - PL - PR);
  const ty = (y: number) => PT + (1 - (y - minY) / rangeY) * (H - PT - PB);

  const path1 = series1.length < 2 ? "" : series1.map((p, i) => `${i === 0 ? "M" : "L"} ${tx(p.x).toFixed(1)},${ty(p.y).toFixed(1)}`).join(" ");
  const path2 = series2.length < 2 ? "" : series2.map((p, i) => `${i === 0 ? "M" : "L"} ${tx(p.x).toFixed(1)},${ty(p.y).toFixed(1)}`).join(" ");

  const fill1 = series1.length >= 2
    ? `M ${tx(series1[0].x).toFixed(1)},${H - PB} ${series1.map(p => `L ${tx(p.x).toFixed(1)},${ty(p.y).toFixed(1)}`).join(" ")} L ${tx(series1[series1.length - 1].x).toFixed(1)},${H - PB} Z`
    : "";

  const guides = [0.25, 0.5, 0.75, 1].map(t => minY + t * rangeY);
  const zeroY = ty(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={220} style={{ display: "block", overflow: "visible" }}>
      <defs>
        <linearGradient id="chartFill1" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(201,160,74,0.12)" />
          <stop offset="100%" stopColor="rgba(201,160,74,0.00)" />
        </linearGradient>
      </defs>

      {/* Zero line */}
      {zeroY >= PT && zeroY <= H - PB && (
        <line x1={PL} y1={zeroY} x2={W - PR} y2={zeroY} stroke="rgba(255,255,255,0.10)" strokeWidth="0.8" />
      )}

      {/* Guide lines + Y labels */}
      {guides.map((v, i) => (
        <g key={i}>
          <line x1={PL} y1={ty(v)} x2={W - PR} y2={ty(v)} stroke="rgba(255,255,255,0.04)" strokeWidth="0.6" />
          <text x={PL - 4} y={ty(v) + 3.5} fontFamily="var(--font-mono)" fontSize="8" fill="rgba(255,255,255,0.22)" textAnchor="end">
            {yFmt ? yFmt(v) : v.toFixed(0)}
          </text>
        </g>
      ))}

      {/* Baseline (benchmark static line) */}
      {baseline !== undefined && (
        <line
          x1={PL} y1={ty(baseline)} x2={W - PR} y2={ty(baseline)}
          stroke="rgba(255,255,255,0.25)" strokeWidth="1.2" strokeDasharray="5 6"
        />
      )}

      {/* Fill area line 1 */}
      {fill1 && <path d={fill1} fill="url(#chartFill1)" />}

      {/* Series 2 (benchmark dynamic) */}
      {path2 && (
        <path d={path2} fill="none" stroke="rgba(255,255,255,0.30)" strokeWidth="1.5"
              strokeLinejoin="round" strokeLinecap="round" strokeDasharray="6 5" />
      )}

      {/* Series 1 (TippeIQ) */}
      {path1 && (
        <path ref={lineRef} d={path1} fill="none" stroke="var(--gold)" strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />
      )}

      {/* Endpoint dot series 1 */}
      {series1.length > 0 && (() => {
        const last = series1[series1.length - 1];
        return <circle cx={tx(last.x)} cy={ty(last.y)} r="3.5" fill="var(--gold)" />;
      })()}
    </svg>
  );
}

// ── Section header ────────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: string }) {
  return (
    <div style={{
      fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700,
      letterSpacing: "0.16em", color: "var(--tx-4)", marginBottom: 4,
      textTransform: "uppercase",
    }}>
      {children}
    </div>
  );
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{
      fontFamily: "var(--font-heading)", fontSize: 22, fontWeight: 800,
      color: "var(--tx-1)", letterSpacing: "-0.03em", margin: "0 0 20px 0",
    }}>
      {children}
    </h2>
  );
}

// ── Model vs Benchmark visual ─────────────────────────────────────────────────

function VsBlock({ leftLabel, leftValue, leftColor, rightLabel, rightValue, rightColor, diffLabel }: {
  leftLabel: string; leftValue: string; leftColor: string;
  rightLabel: string; rightValue: string; rightColor: string;
  diffLabel: string;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
      <div style={{ flex: 1, padding: "28px 32px", textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: leftColor, opacity: 0.7, marginBottom: 10 }}>
          {leftLabel}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 44, fontWeight: 800, color: leftColor, letterSpacing: "-0.05em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {leftValue}
        </div>
      </div>
      <div style={{ padding: "0 24px", textAlign: "center", flexShrink: 0 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--tx-4)", letterSpacing: "0.08em", marginBottom: 6 }}>vs</div>
        <div style={{ width: 1, height: 48, background: "rgba(255,255,255,0.08)", margin: "0 auto" }} />
      </div>
      <div style={{ flex: 1, padding: "28px 32px", textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: rightColor, opacity: 0.7, marginBottom: 10 }}>
          {rightLabel}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 44, fontWeight: 800, color: rightColor, letterSpacing: "-0.05em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {rightValue}
        </div>
      </div>
      <div style={{ padding: "0 24px 0 32px", flexShrink: 0 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.10em", color: "var(--tx-4)", marginBottom: 6 }}>FORDEL</div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 20, fontWeight: 800, color: "var(--gold)", fontVariantNumeric: "tabular-nums" }}>
          {diffLabel}
        </div>
      </div>
    </div>
  );
}

// ── Stat card (best/worst) ────────────────────────────────────────────────────

function StatCard({ label, value, sub, valueColor }: { label: string; value: string; sub?: string; valueColor?: string }) {
  return (
    <div style={{
      flex: 1, padding: "24px 24px 22px",
      background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14,
    }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 12 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 28, fontWeight: 800, color: valueColor ?? "var(--tx-1)", letterSpacing: "-0.04em", lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </div>
      {sub && <div style={{ fontFamily: "var(--font-sans)", fontSize: 12, color: "var(--tx-4)", marginTop: 8, lineHeight: 1.4 }}>{sub}</div>}
    </div>
  );
}

// ── Distribution bar ──────────────────────────────────────────────────────────

function DistBar({ label, value, total, color, sub }: { label: string; value: number; total: number; color: string; sub?: string }) {
  const pct = total > 0 ? Math.abs(value) / total : 0;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontFamily: "var(--font-sans)", fontSize: 13, fontWeight: 600, color: "var(--tx-2)" }}>{label}</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color, fontVariantNumeric: "tabular-nums" }}>
          {sub ?? `${value >= 0 ? "+" : ""}${value.toFixed(1)}%`}
        </span>
      </div>
      <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,0.06)", overflow: "hidden", position: "relative" }}>
        <div style={{
          position: "absolute", inset: 0,
          background: color, borderRadius: 3,
          transform: `scaleX(${Math.min(pct, 1)})`, transformOrigin: "left",
          transition: "transform 0.8s cubic-bezier(0.16,1,0.3,1)",
        }} />
      </div>
    </div>
  );
}

// ── Timeline bar chart ────────────────────────────────────────────────────────

type Period = "week" | "month" | "all";

function TimelineChart({ coupons, period }: { coupons: HistoryCouponItem[]; period: Period }) {
  const evaluated = coupons.filter(c => c.correct_picks !== null);
  if (evaluated.length === 0) return (
    <div style={{ height: 120, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--tx-4)" }}>
        Ingen evaluerte kuponger ennå
      </span>
    </div>
  );

  interface Bar { label: string; value: number; count: number }
  let bars: Bar[] = [];

  if (period === "week") {
    bars = evaluated.slice(-12).map(c => ({
      label: `U${c.week}`,
      value: c.hit_rate ?? 0,
      count: 1,
    }));
  } else if (period === "month") {
    const byMonth: Record<string, { sum: number; count: number }> = {};
    for (const c of evaluated) {
      const d = new Date(c.deadline_utc);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      if (!byMonth[key]) byMonth[key] = { sum: 0, count: 0 };
      byMonth[key].sum += (c.hit_rate ?? 0);
      byMonth[key].count++;
    }
    bars = Object.entries(byMonth).slice(-8).map(([k, v]) => ({
      label: k.slice(5) + "/" + k.slice(2, 4),
      value: v.count > 0 ? v.sum / v.count : 0,
      count: v.count,
    }));
  } else {
    const avg = evaluated.reduce((s, c) => s + (c.hit_rate ?? 0), 0) / evaluated.length;
    bars = [{ label: "Alle kuponger", value: avg, count: evaluated.length }];
  }

  const maxVal = Math.max(...bars.map(b => b.value), 8);
  const H = 120, W = 100;

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: H + 20 }}>
      {bars.map((bar, i) => {
        const barH = (bar.value / maxVal) * H;
        const isGood = bar.value >= 7;
        const color = isGood ? "var(--gold)" : bar.value >= 5 ? "rgba(201,160,74,0.45)" : "rgba(200,85,78,0.50)";
        return (
          <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: isGood ? "var(--gold)" : "var(--tx-4)", fontVariantNumeric: "tabular-nums" }}>
              {bar.value.toFixed(1)}
            </span>
            <div style={{ width: "100%", height: H, position: "relative", overflow: "hidden" }}>
              <div style={{
                position: "absolute", bottom: 0, left: 0, right: 0, height: "100%",
                background: color, borderRadius: "3px 3px 0 0",
                transform: `scaleY(${barH / H})`, transformOrigin: "bottom",
              }} />
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--tx-4)" }}>{bar.label}</span>
          </div>
        );
      })}
    </div>
  );
}

// ── Transparency row ──────────────────────────────────────────────────────────

function AuditRow({ item, i }: { item: HistoryCouponItem; i: number }) {
  const evaluated = item.evaluation_status === "evaluated";
  const pending   = item.evaluation_status === "pending";
  const won       = (item.correct_picks ?? 0) === 12;
  const good      = (item.hit_rate ?? 0) >= 8;
  const statusColor = won ? "var(--gold)" : good ? "var(--green)" : evaluated ? "var(--tx-3)" : "var(--tx-4)";
  const statusLabel = !evaluated ? "Avventer" : won ? "12/12 — JACKPOT" : `${item.correct_picks ?? "?"}/${item.total_fixtures ?? 12} riktige`;
  const d = new Date(item.deadline_utc);
  const dateStr = d.toLocaleDateString("nb-NO", { day: "2-digit", month: "short", year: "numeric" });

  return (
    <div style={{
      display: "grid", gridTemplateColumns: "32px 1fr 80px 90px 60px",
      padding: "12px 0", gap: 16, alignItems: "center",
      borderBottom: "1px solid rgba(255,255,255,0.04)",
    }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", textAlign: "right" }}>
        #{item.week}
      </span>
      <div>
        <span style={{ fontFamily: "var(--font-heading)", fontSize: 13, fontWeight: 600, color: "var(--tx-1)" }}>
          {item.label}
        </span>
        <span style={{ marginLeft: 8, fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
          {item.strategy?.toUpperCase() ?? ""}
        </span>
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>{dateStr}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: statusColor }}>{statusLabel}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", textAlign: "right" }}>
        {item.total_rows > 0 ? `${item.total_rows} rader` : ""}
      </span>
    </div>
  );
}

// ── Kupong history view ───────────────────────────────────────────────────────

function KupongHistory({ coupons, strategies, ntComp, genAnalytics }: {
  coupons: HistoryCouponItem[];
  strategies: StrategyPerformance[];
  ntComp: { n_total: number; n_model: number; n_nt: number } | null;
  genAnalytics: GenerationAnalytics[];
}) {
  const [period, setPeriod] = useState<Period>("week");
  const evaluated = coupons.filter(c => c.correct_picks !== null);

  const avgHitRate   = evaluated.length > 0 ? evaluated.reduce((s, c) => s + (c.hit_rate ?? 0), 0) / evaluated.length : 0;
  const avgNtHitRate = strategies.length > 0
    ? strategies.filter(s => s.avg_nt_hit_rate !== null).reduce((s, p) => s + (p.avg_nt_hit_rate ?? 0), 0)
    / strategies.filter(s => s.avg_nt_hit_rate !== null).length
    : null;
  const totalCoupons = coupons.length;
  const avgPvr       = strategies.length > 0 ? strategies.reduce((s, p) => s + (p.avg_pvr ?? 0), 0) / strategies.length : null;

  // ROI from generation analytics (combined across strategies)
  const evalGen      = genAnalytics.filter(g => g.n_evaluated > 0);
  const roiAll       = evalGen.length > 0
    ? evalGen.reduce((s, g) => s + ((g.roi ?? 0) * g.n_evaluated), 0) / evalGen.reduce((s, g) => s + g.n_evaluated, 0)
    : null;

  // Chart data: TippeIQ hit rate per coupon (sorted by deadline)
  const sorted = [...evaluated].sort((a, b) => new Date(a.deadline_utc).getTime() - new Date(b.deadline_utc).getTime());
  const series1: { x: number; y: number }[] = sorted.map((c, i) => ({ x: i, y: c.hit_rate ?? 0 }));
  const ntBaseline = avgNtHitRate;

  // Best/worst
  const bestCoupon  = evaluated.reduce<HistoryCouponItem | null>((b, c) => !b || (c.hit_rate ?? 0) > (b.hit_rate ?? 0) ? c : b, null);
  const worstCoupon = evaluated.reduce<HistoryCouponItem | null>((w, c) => !w || (c.hit_rate ?? 0) < (w.hit_rate ?? 0) ? c : w, null);

  // Best streak: consecutive hit_rate ≥ 7
  let maxStreak = 0, cur = 0;
  for (const c of sorted) { if ((c.hit_rate ?? 0) >= 7) { cur++; maxStreak = Math.max(maxStreak, cur); } else cur = 0; }

  const modelAdvantage = ntComp
    ? ((ntComp.n_model - ntComp.n_nt) / Math.max(ntComp.n_total, 1) * 12).toFixed(1)
    : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 48 }}>

      {/* Hero counters */}
      <div style={{ display: "flex", gap: 32, padding: "40px 0" }}>
        <HeroTile label="SNITT RIKTIGE VALG" raw={avgHitRate} formatted={v => `${v.toFixed(1)}/12`} sub={`${evaluated.length} evaluerte kuponger`} color="var(--gold)" huge />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="FOLKEMENGDENS SNITT" raw={avgNtHitRate ?? 0} formatted={v => avgNtHitRate !== null ? `${v.toFixed(1)}/12` : "—"} sub="NT public gjennomsnitt" color="var(--tx-3)" delay={150} />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="KUPONGER GENERERT" raw={totalCoupons} formatted={v => String(Math.round(v))} sub={`${evaluated.length} evaluert, ${totalCoupons - evaluated.length} avventer`} delay={250} />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="PREMIEANDEL (PVR)" raw={avgPvr ?? 0} formatted={v => avgPvr !== null ? v.toFixed(2) : "—"} sub="snitt over alle kuponger" color={avgPvr && avgPvr >= 1 ? "var(--green)" : "var(--tx-3)"} delay={350} />
      </div>

      {/* Dual-line chart */}
      <section>
        <SectionLabel>Ytelseskurve</SectionLabel>
        <SectionTitle>TippeIQ vs. Folkemengden</SectionTitle>
        <div style={{
          background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16,
          padding: "24px 24px 12px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div style={{ display: "flex", gap: 20 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 2, background: "var(--gold)", display: "inline-block" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)" }}>TippeIQ</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 2, background: "rgba(255,255,255,0.35)", display: "inline-block", borderTop: "2px dashed rgba(255,255,255,0.35)" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>Folkemengden</span>
              </span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
              Antall riktige valg (0–12)
            </span>
          </div>

          {evaluated.length >= 2 ? (
            <DualLineChart
              series1={series1}
              series2={[]}
              baseline={avgNtHitRate ?? undefined}
              label1="TippeIQ" label2="Folkemengden"
              yFmt={v => v.toFixed(1)}
            />
          ) : (
            <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--tx-3)", marginBottom: 8 }}>
                  Ikke nok data ennå
                </div>
                <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                  Kurven vises etter at minst 2 kuponger er evaluert.
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Model vs Benchmark */}
      {ntComp && ntComp.n_total > 0 && (
        <section>
          <SectionLabel>Fordel modell</SectionLabel>
          <SectionTitle>Modell vs. Folkemengden</SectionTitle>
          <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, overflow: "hidden" }}>
            <VsBlock
              leftLabel="TIPPEIQ — SNITT RIKTIGE"
              leftValue={`${(ntComp.n_model / ntComp.n_total * 12).toFixed(1)}/12`}
              leftColor="var(--gold)"
              rightLabel="FOLKEMENGDEN — SNITT RIKTIGE"
              rightValue={`${(ntComp.n_nt / ntComp.n_total * 12).toFixed(1)}/12`}
              rightColor="var(--tx-3)"
              diffLabel={modelAdvantage !== null ? `+${modelAdvantage}` : "—"}
            />
            <div style={{ padding: "0 32px 24px" }}>
              <p style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)", lineHeight: 1.6, margin: 0 }}>
                Over {ntComp.n_total} evaluerte valg har modellen gjennomsnittlig sett
                {modelAdvantage !== null && parseFloat(modelAdvantage) > 0
                  ? ` ${modelAdvantage} flere riktige valg per kupong enn folkemengdens tipps — en statistisk signifikant fordel.`
                  : " lignende resultater som folkemengden — mer data er nødvendig for å se en klar fordel."}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Performance timeline */}
      <section>
        <SectionLabel>Ytelsesforløp</SectionLabel>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <SectionTitle>Riktige valg per periode</SectionTitle>
          <div style={{ display: "flex", gap: 2, padding: "3px", background: "rgba(255,255,255,0.04)", borderRadius: 8, border: "1px solid rgba(255,255,255,0.07)" }}>
            {(["week", "month", "all"] as Period[]).map(p => (
              <button key={p} onClick={() => setPeriod(p)} style={{
                padding: "5px 12px", borderRadius: 6, border: "none", cursor: "pointer",
                background: period === p ? "rgba(255,255,255,0.08)" : "transparent",
                fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: period === p ? 700 : 400,
                color: period === p ? "var(--tx-1)" : "var(--tx-4)", transition: "all 0.12s",
              }}>
                {p === "week" ? "Uke" : p === "month" ? "Mnd" : "Alt"}
              </button>
            ))}
          </div>
        </div>
        <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "24px 24px 20px" }}>
          <TimelineChart coupons={coupons} period={period} />
        </div>
      </section>

      {/* Best / Worst */}
      {evaluated.length > 0 && (
        <section>
          <SectionLabel>Høydepunkter</SectionLabel>
          <SectionTitle>Beste og verste perioder</SectionTitle>
          <div style={{ display: "flex", gap: 12 }}>
            <StatCard
              label="BESTE KUPONG"
              value={bestCoupon ? `${bestCoupon.correct_picks}/12` : "—"}
              sub={bestCoupon?.label ?? ""}
              valueColor="var(--green)"
            />
            <StatCard
              label="VERSTE KUPONG"
              value={worstCoupon ? `${worstCoupon.correct_picks}/12` : "—"}
              sub={worstCoupon?.label ?? ""}
              valueColor="var(--red)"
            />
            <StatCard
              label="BESTE REKKE"
              value={maxStreak > 0 ? `${maxStreak}` : "—"}
              sub={maxStreak > 0 ? `${maxStreak} kuponger ≥ 7/12 på rad` : ""}
              valueColor="var(--gold)"
            />
            <StatCard
              label="ANDEL MED ≥8 RIKTIGE"
              value={evaluated.length > 0
                ? `${Math.round(evaluated.filter(c => (c.hit_rate ?? 0) >= 8).length / evaluated.length * 100)}%`
                : "—"}
              sub={`${evaluated.filter(c => (c.hit_rate ?? 0) >= 8).length} av ${evaluated.length} kuponger`}
            />
          </div>
        </section>
      )}

      {/* Distribution by strategy */}
      {strategies.length > 0 && (
        <section>
          <SectionLabel>Fordeling</SectionLabel>
          <SectionTitle>Resultater per strategi</SectionTitle>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
            <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "24px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 20 }}>
                SNITT RIKTIGE VALG
              </div>
              {strategies.map(s => (
                <DistBar
                  key={s.strategy}
                  label={s.strategy.charAt(0).toUpperCase() + s.strategy.slice(1)}
                  value={s.avg_hit_rate ?? 0}
                  total={12}
                  color="var(--gold)"
                  sub={s.avg_hit_rate !== null ? `${s.avg_hit_rate.toFixed(1)}/12 · ${s.n_coupons} kuponger` : "—"}
                />
              ))}
            </div>
            <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "24px" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em", color: "var(--tx-4)", marginBottom: 20 }}>
                PREMIEANDEL (PVR)
              </div>
              {strategies.map(s => (
                <DistBar
                  key={s.strategy}
                  label={s.strategy.charAt(0).toUpperCase() + s.strategy.slice(1)}
                  value={s.avg_pvr ?? 1}
                  total={2}
                  color={(s.avg_pvr ?? 1) >= 1 ? "var(--green)" : "var(--tx-3)"}
                  sub={s.avg_pvr !== null ? `PVR ${s.avg_pvr.toFixed(2)}` : "—"}
                />
              ))}
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

// ── Odds history view ─────────────────────────────────────────────────────────

function OddsHistory({ summary, bankroll }: { summary: BetSummary | undefined; bankroll: BankrollPoint[] }) {
  const [timeRange, setTimeRange] = useState<"ALL" | "1M" | "3M">("ALL");

  const startBankroll = summary?.starting_bankroll ?? 10_000;
  const currentBankroll = summary?.current_bankroll ?? startBankroll;
  const totalProfit = summary?.total_profit ?? 0;
  const roi = summary?.roi ?? null;
  const hitRate = summary?.hit_rate ?? null;
  const nSettled = (summary?.n_won ?? 0) + (summary?.n_lost ?? 0);

  const isUp = totalProfit >= 0;
  const profitColor = isUp ? "var(--green)" : "var(--red)";

  // Chart: bankroll points vs flat baseline
  const filtered = useMemo(() => {
    if (timeRange === "ALL") return bankroll;
    const days = timeRange === "1M" ? 30 : 90;
    const cutoff = Date.now() - days * 86_400_000;
    const pts = bankroll.filter(p => p.settled_at && new Date(p.settled_at).getTime() >= cutoff);
    return pts.length > 0 ? [bankroll[0], ...pts] : bankroll;
  }, [bankroll, timeRange]);

  const series1 = filtered.map((p, i) => ({ x: i, y: p.bankroll_after }));

  // Best/worst bets from bankroll history
  const profits = bankroll.slice(1).map(p => p.profit_nok ?? 0).filter(p => p !== 0);
  const bestPnl  = profits.length > 0 ? Math.max(...profits) : null;
  const worstPnl = profits.length > 0 ? Math.min(...profits) : null;

  // Drawdown
  let peak = -Infinity, maxDD = 0;
  for (const p of bankroll) {
    if (p.bankroll_after > peak) peak = p.bankroll_after;
    if (peak > 0) maxDD = Math.max(maxDD, (peak - p.bankroll_after) / peak);
  }

  // Market distribution
  const marketData = summary?.by_market ?? {};
  const marketTotal = Object.values(marketData).reduce((s, m) => s + Math.abs(m.profit), 0.001);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 48 }}>

      {/* Hero counters */}
      <div style={{ display: "flex", gap: 32, padding: "40px 0" }}>
        <HeroTile label="ROI" raw={Math.abs(roi ?? 0)} formatted={v => roi !== null ? `${roi >= 0 ? "+" : "−"}${v.toFixed(1)}%` : "—"} sub="avkastning på innsats" color={roi !== null ? (roi >= 0 ? "var(--green)" : "var(--red)") : "var(--tx-3)"} huge />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="TOTAL P/L" raw={Math.abs(totalProfit)} formatted={v => `${totalProfit >= 0 ? "+" : "−"}${v.toFixed(0)} kr`} sub={`Bankroll: ${currentBankroll.toLocaleString("nb-NO")} kr`} color={profitColor} delay={150} />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="AVGJORTE SPILL" raw={nSettled} formatted={v => String(Math.round(v))} sub={`${summary?.n_won ?? 0} vunnet · ${summary?.n_lost ?? 0} tapt`} delay={250} />
        <div style={{ width: 1, background: "rgba(255,255,255,0.06)" }} />
        <HeroTile label="TREFFRATE" raw={hitRate ?? 0} formatted={v => hitRate !== null ? `${v.toFixed(1)}%` : "—"} sub="vunnet / avgjorte" color={hitRate && hitRate >= 50 ? "var(--green)" : "var(--tx-3)"} delay={350} />
      </div>

      {/* Bankroll chart */}
      <section>
        <SectionLabel>Bankrollutvikling</SectionLabel>
        <SectionTitle>TippeIQ vs. Flat betting</SectionTitle>
        <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "24px 24px 12px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div style={{ display: "flex", gap: 20 }}>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 2, background: "var(--gold)", display: "inline-block" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-3)" }}>TippeIQ</span>
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 20, height: 2, background: "rgba(255,255,255,0.35)", display: "inline-block", borderTop: "2px dashed rgba(255,255,255,0.35)" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>Flat betting (break-even)</span>
              </span>
            </div>
            <div style={{ display: "flex", gap: 2, padding: "3px", background: "rgba(255,255,255,0.04)", borderRadius: 7, border: "1px solid rgba(255,255,255,0.07)" }}>
              {(["1M", "3M", "ALL"] as const).map(r => (
                <button key={r} onClick={() => setTimeRange(r)} style={{
                  padding: "4px 10px", borderRadius: 5, border: "none", cursor: "pointer",
                  background: timeRange === r ? "rgba(255,255,255,0.08)" : "transparent",
                  fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: timeRange === r ? 700 : 400,
                  color: timeRange === r ? "var(--tx-1)" : "var(--tx-4)", transition: "all 0.12s",
                }}>{r}</button>
              ))}
            </div>
          </div>

          {filtered.length >= 2 ? (
            <DualLineChart
              series1={series1} series2={[]}
              baseline={startBankroll}
              label1="TippeIQ" label2="Flat"
              yFmt={v => `${(v / 1000).toFixed(0)}k`}
            />
          ) : (
            <div style={{ height: 220, display: "flex", alignItems: "center", justifyContent: "center" }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700, color: "var(--tx-3)", marginBottom: 8 }}>
                  Ikke nok data ennå
                </div>
                <div style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-4)" }}>
                  Kurven vises etter at minst 2 spill er avgjort.
                </div>
              </div>
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)" }}>
              Start {startBankroll.toLocaleString("nb-NO")} kr ·····
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: profitColor, fontVariantNumeric: "tabular-nums" }}>
              {totalProfit >= 0 ? "+" : ""}{totalProfit.toFixed(0)} kr
            </span>
          </div>
        </div>
      </section>

      {/* Model vs Benchmark */}
      <section>
        <SectionLabel>Fordel modell</SectionLabel>
        <SectionTitle>Modell vs. Markedet</SectionTitle>
        <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, overflow: "hidden" }}>
          <VsBlock
            leftLabel="TIPPEIQ ROI"
            leftValue={roi !== null ? `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%` : "—"}
            leftColor={roi !== null ? (roi >= 0 ? "var(--green)" : "var(--red)") : "var(--tx-3)"}
            rightLabel="FLAT BETTING ROI"
            rightValue="0.0%"
            rightColor="var(--tx-4)"
            diffLabel={roi !== null ? `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%` : "—"}
          />
          <div style={{ padding: "0 32px 24px" }}>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 14, color: "var(--tx-3)", lineHeight: 1.6, margin: 0 }}>
              Flat betting på rettferdig odds er break-even over tid. TippeIQ bruker modellkanten til å velge spill med høyere forventet verdi enn markedet priser inn.
            </p>
          </div>
        </div>
      </section>

      {/* Best/Worst */}
      <section>
        <SectionLabel>Høydepunkter</SectionLabel>
        <SectionTitle>Beste og verste perioder</SectionTitle>
        <div style={{ display: "flex", gap: 12 }}>
          <StatCard label="BESTE SPILL" value={bestPnl !== null ? `+${bestPnl.toFixed(0)} kr` : "—"} sub="høyest enkelt-gevinst" valueColor="var(--green)" />
          <StatCard label="VERSTE SPILL" value={worstPnl !== null ? `${worstPnl.toFixed(0)} kr` : "—"} sub="høyest enkelt-tap" valueColor="var(--red)" />
          <StatCard label="MAKS DRAWDOWN" value={maxDD > 0 ? `${(maxDD * 100).toFixed(1)}%` : "—"} sub="fra bankroll-topp" valueColor={maxDD > 0.2 ? "var(--red)" : "var(--tx-1)"} />
          <StatCard label="SNITT CLV" value={summary?.avg_clv !== null && summary?.avg_clv !== undefined ? `${(summary.avg_clv >= 0 ? "+" : "")}${summary.avg_clv.toFixed(1)}%` : "—"} sub="closing line value" valueColor="var(--gold)" />
        </div>
      </section>

      {/* Distribution by market */}
      {Object.keys(marketData).length > 0 && (
        <section>
          <SectionLabel>Fordeling</SectionLabel>
          <SectionTitle>Profit per marked</SectionTitle>
          <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "28px 32px" }}>
            {Object.entries(marketData).map(([market, data]) => (
              <DistBar
                key={market}
                label={market === "1x2" ? "1X2" : market === "btts" ? "BTTS" : market === "over_2.5" ? "Over/Under 2.5" : market}
                value={data.profit}
                total={marketTotal}
                color={data.profit >= 0 ? "var(--green)" : "var(--red)"}
                sub={`${data.profit >= 0 ? "+" : ""}${data.profit.toFixed(0)} kr · ${data.n_won + data.n_lost} spill`}
              />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

// ── Transparency section (shared) ─────────────────────────────────────────────

function TransparencySection({ coupons }: { coupons: HistoryCouponItem[] }) {
  const recent = [...coupons].sort((a, b) => new Date(b.deadline_utc).getTime() - new Date(a.deadline_utc).getTime()).slice(0, 10);
  return (
    <section>
      <SectionLabel>Integritet</SectionLabel>
      <SectionTitle>Transparens og sporbarhet</SectionTitle>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
        {[
          { icon: "⏱", title: "Tidsstemplet", body: "Alle kuponger lagres automatisk med tidsstempel før kampstart. Ingen etterregistrering er mulig." },
          { icon: "🔒", title: "Uendret historikk", body: "Ingen resultater kan redigeres etter at de er lagret. Alle spill beholdes i databasen." },
          { icon: "📊", title: "Fullstendig arkiv", body: "Alle kuponger, tegn og evalueringer er tilgjengelig i sin helhet — inkludert tapende kuponger." },
          { icon: "🧪", title: "Modellbasert", body: "Alle valg er generert av modellen uten menneskelig etterjustering. NT-prosentene påvirker aldri valgene." },
        ].map(item => (
          <div key={item.title} style={{ padding: "22px 24px", background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 14 }}>
            <div style={{ fontSize: 22, marginBottom: 10 }}>{item.icon}</div>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: 14, fontWeight: 700, color: "var(--tx-1)", marginBottom: 6, letterSpacing: "-0.01em" }}>
              {item.title}
            </div>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 13, color: "var(--tx-3)", margin: 0, lineHeight: 1.55 }}>
              {item.body}
            </p>
          </div>
        ))}
      </div>

      {recent.length > 0 && (
        <div style={{ background: "var(--surf-1)", border: "1px solid rgba(255,255,255,0.07)", borderRadius: 16, padding: "20px 24px" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.14em", color: "var(--tx-4)", marginBottom: 16 }}>
            REVISJONSLOGG — SISTE {recent.length} KUPONGER
          </div>
          {recent.map((c, i) => <AuditRow key={c.coupon_id} item={c} i={i} />)}
        </div>
      )}
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HistorikkPage() {
  const [mode, setMode] = useState<Mode>("kupong");

  const { data: coupons = [] } = useQuery({
    queryKey: ["history"],
    queryFn: () => getHistory(),
    staleTime: 5 * 60_000,
  });

  const { data: strategies = [] } = useQuery({
    queryKey: ["history-strategy"],
    queryFn: () => getHistoryStrategyPerformance(),
    staleTime: 5 * 60_000,
  });

  const { data: ntComp } = useQuery({
    queryKey: ["history-nt"],
    queryFn: () => getHistoryNtComparison(),
    staleTime: 5 * 60_000,
  });

  const { data: genAnalytics = [] } = useQuery({
    queryKey: ["gen-analytics"],
    queryFn: () => getStrategyAnalytics(),
    staleTime: 5 * 60_000,
  });

  const { data: summary } = useQuery({
    queryKey: ["bet-summary"],
    queryFn: () => getBetSummary(),
    staleTime: 30_000,
  });

  const { data: bankroll = [] } = useQuery({
    queryKey: ["bankroll"],
    queryFn: () => getBankroll(),
    staleTime: 30_000,
  });

  return (
    <div className="min-h-screen" style={{ marginLeft: 240, background: "var(--canvas)" }}>
      {/* Sticky header */}
      <header style={{
        position: "sticky", top: 0, zIndex: 20,
        background: "var(--surf-0)", borderBottom: "1px solid rgba(255,255,255,0.06)",
        height: 44, display: "flex", alignItems: "center", padding: "0 40px", gap: 14,
      }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, letterSpacing: "0.14em", color: "var(--gold)" }}>
          HISTORIKK
        </span>
        <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.10)" }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--tx-4)", letterSpacing: "0.06em" }}>
          Bevist ytelse over tid
        </span>
      </header>

      <main style={{ maxWidth: 1060, margin: "0 auto", padding: "40px 40px 80px" }}>
        {/* Page title + mode toggle */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 8 }}>
          <div>
            <h1 style={{
              fontFamily: "var(--font-heading)", fontSize: 32, fontWeight: 800,
              color: "var(--tx-1)", letterSpacing: "-0.04em", margin: "0 0 8px",
            }}>
              Fungerer det?
            </h1>
            <p style={{ fontFamily: "var(--font-sans)", fontSize: 15, color: "var(--tx-3)", margin: 0, lineHeight: 1.5 }}>
              Sporbar ytelse mot en objektiv referanse. Ingen editerte resultater — bare tall.
            </p>
          </div>
          <ModeToggle mode={mode} onChange={setMode} />
        </div>

        {/* Mode-specific content */}
        {mode === "kupong" ? (
          <KupongHistory
            coupons={coupons}
            strategies={strategies}
            ntComp={ntComp ?? null}
            genAnalytics={genAnalytics}
          />
        ) : (
          <OddsHistory summary={summary} bankroll={bankroll} />
        )}

        {/* Transparency (always visible) */}
        <div style={{ marginTop: 48 }}>
          <TransparencySection coupons={coupons} />
        </div>
      </main>
    </div>
  );
}
