"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useEffect, useState } from "react";
import { ArrowRight } from "lucide-react";
import { getSignalBoard, getStrategyAnalytics } from "@/lib/api";
import type { MatchSignal } from "@/lib/types";
import { formatUntil } from "@/lib/utils";

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  canvas: "var(--canvas)",
  surf0:  "var(--surf-0)",
  surf1:  "var(--surf-1)",
  surf2:  "var(--surf-2)",
  surf3:  "var(--surf-3)",
  bdr0:   "var(--bdr-0)",
  bdr1:   "var(--bdr-1)",
  bdr2:   "var(--bdr-2)",
  tx1:    "var(--tx-1)",
  tx2:    "var(--tx-2)",
  tx3:    "var(--tx-3)",
  tx4:    "var(--tx-4)",
  gold:   "var(--gold)",
  green:  "var(--green)",
  red:    "var(--red)",
  indigo: "var(--indigo)",
} as const;

// ── Scroll reveal ─────────────────────────────────────────────────────────────
function Reveal({
  children,
  delay = 0,
  style = {},
}: {
  children: React.ReactNode;
  delay?: number;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ob = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setVisible(true); },
      { threshold: 0.06, rootMargin: "0px 0px -24px 0px" },
    );
    ob.observe(el);
    return () => ob.disconnect();
  }, []);
  return (
    <div
      ref={ref}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? "none" : "translateY(24px)",
        transition: `opacity 0.75s ease ${delay}ms, transform 0.75s cubic-bezier(0.22,1,0.36,1) ${delay}ms`,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

// ── Animated counter ──────────────────────────────────────────────────────────
function CountUp({
  to,
  prefix = "",
  suffix = "",
  decimals = 0,
  duration = 1600,
}: {
  to: number;
  prefix?: string;
  suffix?: string;
  decimals?: number;
  duration?: number;
}) {
  const [val, setVal] = useState(0);
  const [fired, setFired] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || fired) return;
    const ob = new IntersectionObserver(
      ([e]) => { if (e.isIntersecting) setFired(true); },
      { threshold: 0.5 },
    );
    ob.observe(el);
    return () => ob.disconnect();
  }, [fired]);

  useEffect(() => {
    if (!fired) return;
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - t0) / duration, 1);
      const ease = 1 - Math.pow(1 - p, 4);
      setVal(to * ease);
      if (p < 1) requestAnimationFrame(tick);
      else setVal(to);
    };
    requestAnimationFrame(tick);
  }, [fired, to, duration]);

  const fmt = decimals > 0 ? val.toFixed(decimals) : Math.round(val).toString();
  return <span ref={ref}>{prefix}{fmt}{suffix}</span>;
}

// ── Team badge — initials with deterministic color ────────────────────────────
function TeamBadge({ name, url, size = 48 }: { name: string; url?: string | null; size?: number }) {
  const [failed, setFailed] = useState(false);
  const initials = name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const hue = Array.from(name).reduce((h, c) => (h * 31 + c.charCodeAt(0)) & 0xFFFF, 0) % 360;
  const showLogo = url && !failed;
  return (
    <div style={{
      width: size, height: size, borderRadius: 5,
      background: `hsl(${hue},22%,16%)`,
      display: "flex", alignItems: "center", justifyContent: "center",
      flexShrink: 0, overflow: "hidden",
    }}>
      {showLogo ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url!} alt={name} width={size} height={size}
          style={{ objectFit: "contain", padding: size * 0.1 }}
          onError={() => setFailed(true)} />
      ) : (
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: size * 0.3,
          fontWeight: 700, color: "rgba(255,255,255,0.60)",
          letterSpacing: "-0.02em",
        }}>{initials}</span>
      )}
    </div>
  );
}

// ── Probability bar ───────────────────────────────────────────────────────────
function ProbBar({
  pct,
  color,
  label,
  right,
  animate = true,
}: {
  pct: number;
  color: string;
  label: string;
  right: string;
  animate?: boolean;
}) {
  const [ready, setReady] = useState(!animate);
  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setReady(true), 300);
    return () => clearTimeout(t);
  }, [animate]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
          letterSpacing: "0.12em", color: C.tx4, textTransform: "uppercase",
        }}>
          {label}
        </span>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700,
          color: C.tx1, fontVariantNumeric: "tabular-nums",
        }}>
          {right}
        </span>
      </div>
      <div style={{
        height: 6, borderRadius: 4, background: "rgba(255,255,255,0.06)",
        overflow: "hidden", position: "relative",
      }}>
        <div style={{
          position: "absolute", inset: 0,
          width: "100%",
          borderRadius: 4, background: color,
          transformOrigin: "left",
          transform: ready ? `scaleX(${Math.min(pct, 100) / 100})` : "scaleX(0)",
          transition: "transform 0.9s cubic-bezier(0.16,1,0.3,1)",
        }} />
      </div>
    </div>
  );
}

// ── Pick label ────────────────────────────────────────────────────────────────
function pickLabel(pick: string) {
  if (pick === "H") return "Hjemmeseier";
  if (pick === "U") return "Uavgjort";
  if (pick === "B") return "Borteseier";
  return pick;
}

// ── Hero signal card ──────────────────────────────────────────────────────────
function HeroSignalCard({ signal }: { signal: MatchSignal | null }) {
  if (!signal) {
    return (
      <div
        className="animate-pulse"
        style={{
          background: C.surf1, border: `1px solid ${C.bdr1}`,
          borderRadius: 20, padding: 32, minHeight: 420,
          display: "flex", flexDirection: "column", gap: 24,
        }}
      >
        <div style={{ height: 10, width: 120, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
        <div style={{ height: 56, width: "55%", borderRadius: 6, background: "rgba(255,255,255,0.09)" }} />
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <div style={{ width: 48, height: 48, borderRadius: 5, background: "rgba(255,255,255,0.07)" }} />
          <div style={{ height: 14, flex: 1, borderRadius: 4, background: "rgba(255,255,255,0.06)" }} />
          <div style={{ width: 48, height: 48, borderRadius: 5, background: "rgba(255,255,255,0.07)" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {[80, 60].map((w, i) => (
            <div key={i} style={{ height: 7, width: `${w}%`, borderRadius: 4, background: "rgba(255,255,255,0.06)" }} />
          ))}
        </div>
      </div>
    );
  }

  const ep       = signal.edge_pp;
  const isPos    = (ep ?? 0) >= 0;
  const hasCrowd = signal.has_public_tips && ep !== null;
  // indigo for crowd-overvalued (negative edge) — not a loss, a counter-signal
  const edgeColor = hasCrowd ? (isPos ? C.gold : C.indigo) : C.tx2;

  return (
    <div
      style={{
        background: C.surf1,
        border: `1px solid rgba(255,255,255,0.09)`,
        borderRadius: 20,
        padding: 32,
        position: "relative",
        overflow: "hidden",
        boxShadow: hasCrowd && isPos
          ? "0 0 48px rgba(201,160,74,0.08), 0 4px 24px rgba(0,0,0,0.4)"
          : hasCrowd && !isPos
          ? "0 0 48px rgba(123,146,255,0.06), 0 4px 24px rgba(0,0,0,0.4)"
          : "0 4px 24px rgba(0,0,0,0.35)",
      }}
    >
      {/* Background glow — gold for positive edge, indigo for counter-signal */}
      {hasCrowd && (
        <div style={{
          position: "absolute", top: -60, right: -60, width: 220, height: 220,
          background: isPos
            ? "radial-gradient(circle, rgba(201,160,74,0.09) 0%, transparent 65%)"
            : "radial-gradient(circle, rgba(123,146,255,0.07) 0%, transparent 65%)",
          pointerEvents: "none",
        }} />
      )}

      {/* League + live */}
      <div style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        marginBottom: 28,
      }}>
        <span style={{
          fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
          letterSpacing: "0.14em", color: C.tx4, textTransform: "uppercase",
        }}>
          {signal.league_name ?? "Norsk Tipping"}
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span className="tq-live-dot" aria-hidden />
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
            color: C.green, letterSpacing: "0.1em",
          }}>LIVE</span>
        </div>
      </div>

      {/* Edge — dominant number */}
      <div style={{
        fontFamily: "var(--font-display)",
        fontSize: "clamp(52px, 5.5vw, 72px)",
        fontWeight: 900,
        letterSpacing: "-0.05em",
        lineHeight: 1,
        color: edgeColor,
        fontVariantNumeric: "tabular-nums",
        marginBottom: 6,
      }}>
        {hasCrowd && ep !== null
          ? `${isPos ? "+" : ""}${Math.abs(ep).toFixed(1)}pp`
          : `${signal.model_prob}%`}
      </div>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.10em",
        color: C.tx4, marginBottom: 28,
      }}>
        {hasCrowd
          ? isPos ? "UNDERPRISET AV FOLKET" : "OVERPRISET AV FOLKET"
          : "MODELL-SANNSYNLIGHET"}
      </div>

      {/* Teams */}
      <div style={{
        display: "flex", alignItems: "center", gap: 14, marginBottom: 28,
      }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
          <TeamBadge name={signal.home_team} url={signal.home_logo_url} size={44} />
          <span style={{
            fontFamily: "var(--font-heading)", fontSize: 11, fontWeight: 600,
            color: C.tx3, maxWidth: 72, textAlign: "center",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {signal.home_team.split(" ")[0]}
          </span>
        </div>
        <div style={{ flex: 1, textAlign: "center" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: C.tx4, letterSpacing: "0.1em" }}>VS</span>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
          <TeamBadge name={signal.away_team} url={signal.away_logo_url} size={44} />
          <span style={{
            fontFamily: "var(--font-heading)", fontSize: 11, fontWeight: 600,
            color: C.tx3, maxWidth: 72, textAlign: "center",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>
            {signal.away_team.split(" ")[0]}
          </span>
        </div>
      </div>

      {/* Probability bars */}
      {hasCrowd && signal.pub_prob !== null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 22 }}>
          <ProbBar
            pct={signal.model_prob}
            color={C.gold}
            label="Modell"
            right={`${signal.model_prob}%`}
            animate
          />
          <ProbBar
            pct={signal.pub_prob}
            color="rgba(255,255,255,0.18)"
            label="Folket"
            right={`${Math.round(signal.pub_prob)}%`}
            animate
          />
        </div>
      )}

      {/* Pick badge */}
      <div style={{
        display: "flex", alignItems: "center", gap: 10,
        paddingTop: 18, borderTop: `1px solid ${C.bdr0}`,
      }}>
        <div style={{
          width: 28, height: 28, borderRadius: 7,
          background: hasCrowd && isPos ? C.gold : hasCrowd && !isPos ? "rgba(123,146,255,0.15)" : "rgba(255,255,255,0.08)",
          border: hasCrowd && isPos ? "none" : hasCrowd && !isPos ? "1px solid rgba(123,146,255,0.25)" : `1px solid rgba(255,255,255,0.14)`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 800,
            color: hasCrowd && isPos ? "#0A0A0B" : hasCrowd && !isPos ? C.indigo : C.tx1,
          }}>
            {signal.recommended_pick}
          </span>
        </div>
        <span style={{
          fontFamily: "var(--font-heading)", fontSize: 14, fontWeight: 600,
          color: C.tx1, letterSpacing: "-0.01em",
        }}>
          {pickLabel(signal.recommended_pick)}
        </span>
        <div style={{ flex: 1 }} />
        <Link
          href="/signaler"
          style={{
            fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
            color: C.gold, textDecoration: "none", letterSpacing: "0.04em",
            display: "flex", alignItems: "center", gap: 4,
          }}
        >
          Analyse <ArrowRight size={10} strokeWidth={2.5} />
        </Link>
      </div>
    </div>
  );
}

// ── How it works card ─────────────────────────────────────────────────────────
function HowCard({
  step, label, value, valueSub, desc, accent = C.tx1,
}: {
  step: string; label: string; value: string;
  valueSub: string; desc: string; accent?: string;
}) {
  return (
    <div style={{
      background: C.surf1,
      border: `1px solid ${C.bdr1}`,
      borderRadius: 18,
      padding: "36px 32px",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{
        fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
        letterSpacing: "0.18em", color: "rgba(201,160,74,0.40)",
        marginBottom: 14,
      }}>
        {step}
      </div>
      <div style={{
        fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 600,
        color: C.tx3, letterSpacing: "-0.01em", marginBottom: 28,
      }}>
        {label}
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(44px, 4.5vw, 60px)",
          fontWeight: 900, letterSpacing: "-0.05em",
          lineHeight: 1, color: accent,
          fontVariantNumeric: "tabular-nums",
        }}>
          {value}
        </div>
        <div style={{
          fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.12em",
          color: C.tx4, marginTop: 6, textTransform: "uppercase",
        }}>
          {valueSub}
        </div>
      </div>
      <div style={{
        fontFamily: "var(--font-sans)", fontSize: 14, lineHeight: 1.75,
        color: C.tx3, marginTop: "auto", paddingTop: 24,
        borderTop: `1px solid ${C.bdr0}`,
      }}>
        {desc}
      </div>
    </div>
  );
}

// ── Trust item ────────────────────────────────────────────────────────────────
function TrustItem({
  icon, title, desc,
}: {
  icon: React.ReactNode; title: string; desc: string;
}) {
  return (
    <div style={{
      display: "flex", gap: 20,
      padding: "28px 24px",
      background: C.surf1,
      border: `1px solid ${C.bdr1}`,
      borderRadius: 16,
    }}>
      <div style={{
        width: 40, height: 40, borderRadius: 10,
        background: C.surf2, border: `1px solid ${C.bdr1}`,
        display: "flex", alignItems: "center", justifyContent: "center",
        flexShrink: 0, color: C.gold,
      }}>
        {icon}
      </div>
      <div>
        <div style={{
          fontFamily: "var(--font-heading)", fontSize: 15, fontWeight: 700,
          color: C.tx1, letterSpacing: "-0.015em", marginBottom: 8,
        }}>
          {title}
        </div>
        <div style={{
          fontFamily: "var(--font-sans)", fontSize: 14, lineHeight: 1.7,
          color: C.tx3,
        }}>
          {desc}
        </div>
      </div>
    </div>
  );
}

// ── SVG icons ─────────────────────────────────────────────────────────────────
const IconShield = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
    <path d="M8 1.5 L14 4v4c0 3.5-2.5 6-6 7C2 14 0 11.5 0 8V4z" fill="none" stroke="currentColor" strokeWidth="1.3"/>
    <path d="M5 8l2 2 4-3.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);
const IconEye = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
    <path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" stroke="currentColor" strokeWidth="1.3"/>
    <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/>
  </svg>
);
const IconTarget = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
    <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3"/>
    <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.3"/>
    <circle cx="8" cy="8" r="1" fill="currentColor"/>
  </svg>
);
const IconChart = () => (
  <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
    <rect x="2.5" y="8.5" width="2.6" height="5" rx="0.6" fill="currentColor"/>
    <rect x="6.7" y="5.5" width="2.6" height="8" rx="0.6" fill="currentColor"/>
    <rect x="10.9" y="3" width="2.6" height="10.5" rx="0.6" fill="currentColor"/>
  </svg>
);

// ── Page ──────────────────────────────────────────────────────────────────────
export default function HomePage() {
  const { data, isLoading } = useQuery({
    queryKey: ["signal-board"],
    queryFn: () => getSignalBoard(),
    staleTime: 60_000,
    retry: 1,
  });

  const { data: analytics } = useQuery({
    queryKey: ["strategy-analytics"],
    queryFn: getStrategyAnalytics,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const topSignal  = data?.signals.find(s => s.has_public_tips && (s.edge_pp ?? 0) > 0) ?? data?.signals[0] ?? null;
  const nSignals   = data?.signals.length ?? 0;
  const nStrong    = data?.signals.filter(s => (s.edge_pp ?? 0) >= 8).length ?? 0;

  // For the "How it works" section — derive live metrics from signals
  const signalsWithCrowd = data?.signals.filter(s => s.has_public_tips && s.pub_prob !== null) ?? [];
  const avgCrowd  = signalsWithCrowd.length
    ? Math.round(signalsWithCrowd.reduce((s, m) => s + (m.pub_prob ?? 0), 0) / signalsWithCrowd.length)
    : 56;
  const avgModel  = signalsWithCrowd.length
    ? Math.round(signalsWithCrowd.reduce((s, m) => s + m.model_prob, 0) / signalsWithCrowd.length)
    : 67;
  const avgEdge   = signalsWithCrowd.length
    ? signalsWithCrowd.reduce((s, m) => s + (m.edge_pp ?? 0), 0) / signalsWithCrowd.length
    : 9.2;

  // Proof stats from GenerationAnalytics (balanced strategy)
  const bal = analytics?.find(a => a.strategy === "balanced");

  return (
    <div style={{ marginLeft: 240, background: C.canvas, overflowX: "hidden" }}>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* HERO                                                                  */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          position: "relative",
          overflow: "hidden",
        }}
      >
        {/* Radial gold atmosphere */}
        <div
          aria-hidden
          style={{
            position: "absolute", top: "-15%", right: "-5%",
            width: "55vw", height: "55vw",
            background: "radial-gradient(circle, rgba(201,160,74,0.07) 0%, transparent 60%)",
            pointerEvents: "none",
          }}
        />

        <div
          style={{
            width: "100%",
            maxWidth: 1200,
            margin: "0 auto",
            padding: "100px 64px 80px",
            display: "flex",
            gap: 80,
            alignItems: "center",
          }}
        >
          {/* ── Left column ── */}
          <div style={{ flex: "1 1 0", minWidth: 0 }}>

            {/* Eyebrow */}
            <div
              className="animate-hero-up"
              style={{
                display: "flex", alignItems: "center", gap: 10,
                marginBottom: 44,
              }}
            >
              <span className="tq-live-dot" aria-hidden />
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: 11,
                color: C.tx4, letterSpacing: "0.08em",
              }}>
                Fotball-intelligens · modellen er aktiv
              </span>
            </div>

            {/* Headline */}
            <h1
              className="animate-hero-up"
              style={{
                fontFamily: "var(--font-display)",
                fontSize: "clamp(48px, 5.2vw, 72px)",
                fontWeight: 900,
                letterSpacing: "-0.04em",
                lineHeight: 1.08,
                color: C.tx1,
                margin: "0 0 32px",
                maxWidth: 580,
                animationDelay: "60ms",
              }}
            >
              Norsk Tipping betaler dem som ser det folket overser.
            </h1>

            {/* Subtext */}
            <p
              className="animate-hero-up"
              style={{
                fontFamily: "var(--font-sans)",
                fontSize: 18,
                lineHeight: 1.72,
                color: C.tx2,
                maxWidth: 460,
                margin: "0 0 44px",
                animationDelay: "120ms",
              }}
            >
              Premien deles mellom de som spiller riktig. Spiller du det alle andre spiller, er du én av mange. Spiller du det modellen ser og folket overser, er du én av få.
            </p>

            {/* Live counters */}
            <div
              className="animate-hero-up"
              style={{
                display: "flex", alignItems: "center",
                gap: 24, marginBottom: 48,
                animationDelay: "160ms",
              }}
            >
              {isLoading ? (
                <div className="animate-pulse" style={{ display: "flex", gap: 16 }}>
                  {[60, 80, 72].map((w, i) => (
                    <div key={i} style={{ height: 13, width: w, borderRadius: 4, background: "rgba(255,255,255,0.07)" }} />
                  ))}
                </div>
              ) : data ? (
                <>
                  <div>
                    <div style={{
                      fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 700,
                      color: C.tx1, lineHeight: 1, fontVariantNumeric: "tabular-nums",
                    }}>
                      {nSignals}
                    </div>
                    <div style={{
                      fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.12em",
                      color: C.tx4, marginTop: 5, textTransform: "uppercase",
                    }}>
                      Kamper analysert
                    </div>
                  </div>
                  <div style={{ width: 1, height: 40, background: C.bdr1, flexShrink: 0 }} />
                  <div>
                    <div style={{
                      fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 700,
                      color: nStrong > 0 ? C.gold : C.tx3,
                      lineHeight: 1, fontVariantNumeric: "tabular-nums",
                    }}>
                      {nStrong}
                    </div>
                    <div style={{
                      fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.12em",
                      color: C.tx4, marginTop: 5, textTransform: "uppercase",
                    }}>
                      Sterke signal
                    </div>
                  </div>
                  {data.deadline_utc && (
                    <>
                      <div style={{ width: 1, height: 40, background: C.bdr1, flexShrink: 0 }} />
                      <div>
                        <div style={{
                          fontFamily: "var(--font-mono)", fontSize: 16, fontWeight: 600,
                          color: C.tx2, lineHeight: 1,
                        }}>
                          {formatUntil(data.deadline_utc)}
                        </div>
                        <div style={{
                          fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.12em",
                          color: C.tx4, marginTop: 5, textTransform: "uppercase",
                        }}>
                          Til kupong-frist
                        </div>
                      </div>
                    </>
                  )}
                </>
              ) : null}
            </div>

            {/* CTAs */}
            <div
              className="animate-hero-up"
              style={{ display: "flex", gap: 12, flexWrap: "wrap", animationDelay: "200ms" }}
            >
              <Link
                href="/signaler"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  background: C.gold, color: "#0A0A0B",
                  padding: "15px 30px", borderRadius: 12,
                  fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 700,
                  textDecoration: "none", letterSpacing: "-0.01em",
                  transition: "opacity 0.15s",
                }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.opacity = "0.85")}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.opacity = "1")}
              >
                Se dagens signaler
                <ArrowRight size={15} strokeWidth={2.5} />
              </Link>
              <Link
                href="/kupong"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  color: C.tx2, border: `1px solid ${C.bdr2}`,
                  padding: "15px 30px", borderRadius: 12,
                  fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 500,
                  textDecoration: "none", letterSpacing: "-0.01em",
                  transition: "color 0.15s, border-color 0.15s",
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.color = C.tx1;
                  (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.20)";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.color = C.tx2;
                  (e.currentTarget as HTMLElement).style.borderColor = C.bdr2;
                }}
              >
                Åpne kupong
              </Link>
            </div>
          </div>

          {/* ── Right column: hero signal card ── */}
          <div
            className="animate-hero-up"
            style={{ width: 400, flexShrink: 0, animationDelay: "140ms" }}
          >
            <HeroSignalCard signal={isLoading ? null : topSignal} />
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* SECTION 1: HOW IT WORKS                                              */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section style={{ background: C.surf0, borderTop: `1px solid ${C.bdr0}` }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "100px 64px" }}>

          <Reveal>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.18em", color: C.tx4, textTransform: "uppercase",
              marginBottom: 20,
            }}>
              Slik funker det
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 560, marginBottom: 60 }}>
              <h2 style={{
                fontFamily: "var(--font-display)",
                fontSize: "clamp(36px, 4vw, 52px)",
                fontWeight: 900, letterSpacing: "-0.045em",
                lineHeight: 1, color: C.tx1, margin: 0,
              }}>
                Folket. Modellen.{" "}
                <span style={{ color: C.gold }}>Verdien.</span>
              </h2>
              <p style={{
                fontFamily: "var(--font-sans)", fontSize: 17, lineHeight: 1.72,
                color: C.tx3, margin: 0,
              }}>
                TippeIQ avdekker systematiske feil i folkemengdens fordeling — der folk flest er feil, vinner du mer per riktig kupong.
              </p>
            </div>
          </Reveal>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            <Reveal delay={0}>
              <HowCard
                step="01 — FOLKET"
                label="Hva folkemengden spiller"
                value={signalsWithCrowd.length ? `${avgCrowd}%` : "56%"}
                valueSub="Snitt folkebetting denne uka"
                desc="Norsk Tipping publiserer prosentene for hvert utfall i kupongene. Dette er markedets beste mål på hva folk tror — men ikke nødvendigvis hva som er riktig."
                accent={C.tx2}
              />
            </Reveal>
            <Reveal delay={80}>
              <HowCard
                step="02 — MODELLEN"
                label="Hva modellen beregner"
                value={signalsWithCrowd.length ? `${avgModel}%` : "67%"}
                valueSub="Snitt modell-sannsynlighet"
                desc="Modellen bruker skarpe bookmaker-odds (≥87% vekt) justert for form og statistikk. Den er uavhengig av folkemengden — den ser kun sannsynligheter."
                accent={C.tx1}
              />
            </Reveal>
            <Reveal delay={160}>
              <HowCard
                step="03 — VERDIEN"
                label="Gapet som skaper verdi"
                value={signalsWithCrowd.length ? `+${avgEdge.toFixed(1)}pp` : "+9.2pp"}
                valueSub="Snitt kant mot folket"
                desc="Når modellen ser 67% og folket spiller 56%, betyr det at du — hvis du har rett — deler premien med færre. Det er NT-markedets egenart: verdien finnes i avviket."
                accent={C.gold}
              />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* SECTION 2: WHY THE MODEL EXISTS                                       */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section style={{ background: C.canvas, borderTop: `1px solid ${C.bdr0}` }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "100px 64px" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "start" }}>

            {/* Left: pull quote */}
            <Reveal>
              <div style={{
                fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
                letterSpacing: "0.18em", color: C.tx4, textTransform: "uppercase",
                marginBottom: 28,
              }}>
                Modellens formål
              </div>
              <div style={{
                fontFamily: "var(--font-display)",
                fontSize: "clamp(36px, 3.8vw, 52px)",
                fontWeight: 900, letterSpacing: "-0.045em",
                lineHeight: 1.08, color: C.tx1, marginBottom: 20,
              }}>
                531 441 kombinasjoner. Du velger én.
              </div>
              <div style={{
                fontFamily: "var(--font-display)",
                fontSize: "clamp(28px, 3vw, 40px)",
                fontWeight: 900, letterSpacing: "-0.04em",
                lineHeight: 1.1, color: C.gold,
              }}>
                Velg den som færrest andre velger — og som er riktig.
              </div>
            </Reveal>

            {/* Right: explanation */}
            <Reveal delay={80}>
              <div style={{ display: "flex", flexDirection: "column", gap: 24, paddingTop: 52 }}>
                <p style={{
                  fontFamily: "var(--font-sans)", fontSize: 17, lineHeight: 1.80,
                  color: C.tx2, margin: 0,
                }}>
                  TippeIQ prøver ikke å forutsi fotball perfekt. Det er umulig. Det prøver å finne utfall der <em style={{ color: C.tx1, fontStyle: "normal", fontWeight: 600 }}>folkemengdens prosentandel er lavere enn den reelle sannsynligheten</em>.
                </p>
                <p style={{
                  fontFamily: "var(--font-sans)", fontSize: 17, lineHeight: 1.80,
                  color: C.tx2, margin: 0,
                }}>
                  Norsk Tipping er et poolspill. Premien deles mellom alle vinnerne. Spiller du det alle spiller, er du alltid én av mange — selv om du har rett. Spiller du det modellen identifiserer, er sjansen god for at du er én av få.
                </p>
                <div style={{
                  padding: "20px 24px",
                  background: "rgba(201,160,74,0.05)",
                  border: "1px solid rgba(201,160,74,0.18)",
                  borderRadius: 12,
                }}>
                  <p style={{
                    fontFamily: "var(--font-sans)", fontSize: 15, lineHeight: 1.70,
                    color: C.tx2, margin: 0,
                  }}>
                    <span style={{ color: C.tx1, fontWeight: 600 }}>Crowd Disagreement Score (CDS)</span> måler nettopp dette: avstanden mellom folkemengdens fordeling og modellens beregning. Høy CDS = høy potensiell verdi per riktig kupong.
                  </p>
                </div>
              </div>
            </Reveal>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* SECTION 3: PROOF                                                      */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section style={{ background: C.surf0, borderTop: `1px solid ${C.bdr0}` }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "100px 64px" }}>

          <Reveal>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.18em", color: C.tx4, textTransform: "uppercase",
              marginBottom: 20,
            }}>
              Bevist over tid
            </div>
            <h2 style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(36px, 4vw, 52px)",
              fontWeight: 900, letterSpacing: "-0.045em",
              lineHeight: 1, color: C.tx1, margin: "0 0 60px", maxWidth: 520,
            }}>
              Modellen gir ikke bare tips.{" "}
              <span style={{ color: C.gold }}>Den gir dokumenterbar verdi.</span>
            </h2>
          </Reveal>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 48 }}>
            {[
              {
                value: bal?.roi != null ? bal.roi : null,
                label: "ROI — Balansert strategi",
                prefix: bal?.roi != null && bal.roi >= 0 ? "+" : "",
                suffix: "%",
                decimals: 1,
                desc: "Avkastning på investert budsjett over evaluerte kuponger",
                accent: bal?.roi != null && bal.roi >= 0 ? C.green : C.red,
              },
              {
                value: bal?.hit_rate_9 != null ? bal.hit_rate_9 * 100 : null,
                label: "Treffrate — 9+ rette",
                prefix: "",
                suffix: "%",
                decimals: 1,
                desc: "Andel av kuponger med minst 9 riktige av 12 kamper",
                accent: C.tx1,
              },
              {
                value: bal?.avg_pvr != null ? bal.avg_pvr : null,
                label: "Snitt premieandel (PVR)",
                prefix: "",
                suffix: "×",
                decimals: 2,
                desc: "Forventet gevinst vs. gjennomsnittsvinner over alle evalueringer",
                accent: C.gold,
              },
            ].map(({ value, label, prefix, suffix, decimals, desc, accent }, i) => (
              <Reveal key={i} delay={i * 80}>
                <div style={{
                  background: C.surf1,
                  border: `1px solid ${C.bdr1}`,
                  borderRadius: 18,
                  padding: "36px 32px",
                }}>
                  <div style={{
                    fontFamily: "var(--font-display)",
                    fontSize: "clamp(44px, 4.5vw, 60px)",
                    fontWeight: 900, letterSpacing: "-0.05em",
                    lineHeight: 1, fontVariantNumeric: "tabular-nums",
                    color: value != null ? accent : C.tx4,
                    marginBottom: 6,
                  }}>
                    {value != null ? (
                      <CountUp to={value} prefix={prefix} suffix={suffix} decimals={decimals} />
                    ) : "—"}
                  </div>
                  <div style={{
                    fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.10em",
                    color: C.tx4, textTransform: "uppercase", marginBottom: 24,
                  }}>
                    {label}
                  </div>
                  <div style={{
                    fontFamily: "var(--font-sans)", fontSize: 14, lineHeight: 1.7,
                    color: C.tx3,
                    borderTop: `1px solid ${C.bdr0}`,
                    paddingTop: 20,
                  }}>
                    {desc}
                  </div>
                </div>
              </Reveal>
            ))}
          </div>

          {/* Evaluation note */}
          {(!bal || bal.n_evaluated === 0) && (
            <Reveal delay={240}>
              <div style={{
                padding: "18px 24px",
                background: C.surf1,
                border: `1px solid ${C.bdr1}`,
                borderRadius: 12,
                display: "flex", alignItems: "center", gap: 12,
              }}>
                <div style={{ width: 6, height: 6, borderRadius: "50%", background: C.gold, flexShrink: 0 }} />
                <span style={{
                  fontFamily: "var(--font-sans)", fontSize: 13,
                  color: C.tx3, lineHeight: 1.5,
                }}>
                  Evalueringsdata akkumulerer over tid. Etter 3–5 spilte kuponger vil reelle tall vises her. Evalueringssystemet er live — se <Link href="/historikk" style={{ color: C.gold, textDecoration: "none" }}>Historikk</Link> for status.
                </span>
              </div>
            </Reveal>
          )}
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* SECTION 4: TRUST                                                      */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section style={{ background: C.canvas, borderTop: `1px solid ${C.bdr0}` }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", padding: "100px 64px" }}>

          <Reveal>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.18em", color: C.tx4, textTransform: "uppercase",
              marginBottom: 20,
            }}>
              Hvorfor stole på TippeIQ
            </div>
            <h2 style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(36px, 4vw, 52px)",
              fontWeight: 900, letterSpacing: "-0.045em",
              lineHeight: 1, color: C.tx1,
              margin: "0 0 60px", maxWidth: 500,
            }}>
              Designet for tillit fra grunnen av.
            </h2>
          </Reveal>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Reveal delay={0}>
              <TrustItem
                icon={<IconShield />}
                title="Bookmaker-dominans"
                desc="Modell-sannsynligheten er aldri bedre enn bookmakermarkedet — Pinnacle og øvrige markeder utgjør ≥87% av beregningsgrunnlaget. Vi overskrider ikke markedsestimater, vi justerer ved marginen."
              />
            </Reveal>
            <Reveal delay={60}>
              <TrustItem
                icon={<IconEye />}
                title="Fullstendig uavhengig av folkemengden"
                desc="Modell-sannsynligheten (prob_h/u/b) er matematisk atskilt fra NT-prosentene. Folkemengden brukes kun til å beregne verdien — den påvirker aldri selve sannsynlighetsberegningen."
              />
            </Reveal>
            <Reveal delay={120}>
              <TrustItem
                icon={<IconTarget />}
                title="Pool-optimert, ikke odds-optimert"
                desc="CDS og Pool Value Ratio er spesifikt designet for Norsk Tipping-markedet — ikke for bookmaker-betting. Vi optimaliserer for NT-premiepoolen, der underbetalte utfall gir høyere andel."
              />
            </Reveal>
            <Reveal delay={180}>
              <TrustItem
                icon={<IconChart />}
                title="Transparent og sporbar"
                desc="Alle signal-scores, modell-sannsynligheter og kanttall vises åpent for hvert utfall. Evalueringssystemet logger resultater automatisk for å holde modellen ansvarlig over tid."
              />
            </Reveal>
          </div>
        </div>
      </section>

      {/* ══════════════════════════════════════════════════════════════════════ */}
      {/* SECTION 5: CTA                                                        */}
      {/* ══════════════════════════════════════════════════════════════════════ */}
      <section style={{ background: C.surf0, borderTop: `1px solid ${C.bdr0}`, position: "relative", overflow: "hidden" }}>
        {/* Gold center glow */}
        <div
          aria-hidden
          style={{
            position: "absolute", inset: 0,
            background: "radial-gradient(ellipse 80% 60% at 50% 50%, rgba(201,160,74,0.07) 0%, transparent 70%)",
            pointerEvents: "none",
          }}
        />
        <div style={{
          maxWidth: 800, margin: "0 auto", padding: "120px 64px",
          display: "flex", flexDirection: "column",
          alignItems: "center", textAlign: "center", position: "relative",
        }}>
          <Reveal>
            <div style={{
              fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
              letterSpacing: "0.18em", color: C.tx4, textTransform: "uppercase",
              marginBottom: 28,
            }}>
              Klar?
            </div>
            <h2 style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(44px, 5vw, 68px)",
              fontWeight: 900, letterSpacing: "-0.05em",
              lineHeight: 1.05, color: C.tx1,
              margin: "0 0 24px",
            }}>
              Se det folket overser.
            </h2>
            <p style={{
              fontFamily: "var(--font-sans)", fontSize: 18, lineHeight: 1.70,
              color: C.tx3, margin: "0 0 48px", maxWidth: 460,
            }}>
              {data
                ? `${nSignals} kamper er analysert denne uken.${nStrong > 0 ? ` ${nStrong} sterke signal er identifisert.` : ""} Kupong klar til å optimaliseres.`
                : "Modellen analyserer ukens kamper kontinuerlig. Signal er klare for gjennomgang."}
            </p>
            <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}>
              <Link
                href="/signaler"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  background: C.gold, color: "#0A0A0B",
                  padding: "16px 36px", borderRadius: 14,
                  fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 700,
                  textDecoration: "none", letterSpacing: "-0.01em",
                  transition: "opacity 0.15s",
                }}
                onMouseEnter={e => ((e.currentTarget as HTMLElement).style.opacity = "0.85")}
                onMouseLeave={e => ((e.currentTarget as HTMLElement).style.opacity = "1")}
              >
                Se dagens signaler
                <ArrowRight size={15} strokeWidth={2.5} />
              </Link>
              <Link
                href="/kupong"
                style={{
                  display: "inline-flex", alignItems: "center", gap: 8,
                  color: C.tx2, border: `1px solid ${C.bdr2}`,
                  padding: "16px 36px", borderRadius: 14,
                  fontFamily: "var(--font-sans)", fontSize: 15, fontWeight: 500,
                  textDecoration: "none", letterSpacing: "-0.01em",
                  transition: "color 0.15s, border-color 0.15s",
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.color = C.tx1;
                  (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.20)";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.color = C.tx2;
                  (e.currentTarget as HTMLElement).style.borderColor = C.bdr2;
                }}
              >
                Åpne kupong
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

    </div>
  );
}
