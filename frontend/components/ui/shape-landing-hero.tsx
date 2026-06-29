"use client";

import { motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import Link from "next/link";

// ── Live match data (mirrors real coupon state) ───────────────────────────────

const MATCHES = [
  { home: "Panama",       away: "England",   picks: ["B"],     model: 86, nt: 54, edge: +32 },
  { home: "Kroatia",      away: "Ghana",     picks: ["H","U"], model: 51, nt: 63, edge: -12 },
  { home: "Colombia",     away: "Portugal",  picks: ["U","B"], model: 48, nt: 41, edge:  +7 },
  { home: "Sogndal",      away: "Egersund",  picks: ["H"],     model: 43, nt: 44, edge:  -1 },
  { home: "Strømsgodset", away: "Odd",       picks: ["H"],     model: 59, nt: 56, edge:  +3 },
] as const;

// ── Pick tile ─────────────────────────────────────────────────────────────────

function PickTile({ sign }: { sign: "H" | "U" | "B" }) {
  const config =
    sign === "H" ? { bg: "#F5C030", color: "#0D0D0D" } :
    sign === "U" ? { bg: "#E8E4DD", color: "#0D0D0D" } :
                   { bg: "#22C55E", color: "#0D0D0D" };
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 20,
        height: 20,
        borderRadius: 3,
        flexShrink: 0,
        background: config.bg,
        color: config.color,
        fontSize: 10,
        fontWeight: 800,
        letterSpacing: "0.04em",
        lineHeight: 1,
      }}
    >
      {sign}
    </span>
  );
}

// ── Probability bar — model fill + NT ghost tick ──────────────────────────────

function ProbBar({
  modelPct,
  ntPct,
  pos,
  delay,
}: {
  modelPct: number;
  ntPct: number;
  pos: boolean;
  delay: number;
}) {
  return (
    <div
      className="relative rounded-full"
      style={{ height: 2, background: "rgba(255,255,255,0.06)", marginTop: 8 }}
    >
      <motion.div
        initial={{ width: 0 }}
        animate={{ width: `${modelPct}%` }}
        transition={{ duration: 0.7, delay, ease: [0.0, 0.0, 0.2, 1] }}
        className="absolute inset-y-0 left-0 rounded-full"
        style={{ background: pos ? "#22C55E" : "#F5C030", opacity: 0.6 }}
      />
      {/* NT ghost tick */}
      <div
        className="absolute"
        style={{
          left: `${ntPct}%`,
          top: -3,
          width: 1,
          height: 8,
          background: "rgba(255,255,255,0.2)",
        }}
      />
    </div>
  );
}

// ── Single match row ──────────────────────────────────────────────────────────

function MatchRow({ m, index }: { m: (typeof MATCHES)[number]; index: number }) {
  const pos = m.edge >= 0;
  const animDelay = 0.48 + index * 0.07;

  return (
    <motion.div
      initial={{ opacity: 0, x: 10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: animDelay, duration: 0.36, ease: [0.0, 0.0, 0.2, 1] }}
      className="px-4 py-3"
      style={{ borderTop: index === 0 ? "none" : "1px solid rgba(255,255,255,0.04)" }}
    >
      {/* Line 1: picks · teams · edge */}
      <div className="flex items-center gap-2.5">
        <div className="flex gap-1 shrink-0">
          {(m.picks as readonly string[]).map((p) => (
            <PickTile key={p} sign={p as "H" | "U" | "B"} />
          ))}
        </div>
        <div className="flex-1 min-w-0 flex items-center gap-1">
          <span
            className="text-[12px] font-semibold truncate"
            style={{ fontFamily: "var(--font-display)", color: "#DDDBD8" }}
          >
            {m.home}
          </span>
          <span className="text-[10px] shrink-0" style={{ color: "#252320" }}>—</span>
          <span
            className="text-[12px] font-medium truncate"
            style={{ fontFamily: "var(--font-display)", color: "#555250" }}
          >
            {m.away}
          </span>
        </div>
        <span
          className="text-[11px] font-bold tabular-nums shrink-0"
          style={{ fontFamily: "var(--font-mono)", color: pos ? "#22C55E" : "#F05252" }}
        >
          {pos ? "+" : ""}{m.edge}pp
        </span>
      </div>

      {/* Prob bar + percentage labels */}
      <ProbBar modelPct={m.model} ntPct={m.nt} pos={pos} delay={animDelay + 0.1} />
      <div className="flex justify-between mt-1.5">
        <span
          className="text-[10px] tabular-nums"
          style={{ fontFamily: "var(--font-mono)", color: "#3A3735" }}
        >
          {m.model}%
          <span className="ml-1" style={{ color: "#252320" }}>M</span>
        </span>
        <span
          className="text-[10px] tabular-nums"
          style={{ fontFamily: "var(--font-mono)", color: "#252320" }}
        >
          {m.nt}% NT
        </span>
      </div>
    </motion.div>
  );
}

// ── Left panel: headline + description + CTAs ─────────────────────────────────

function LeftPanel() {
  return (
    <div className="flex flex-col justify-center">
      {/* Live status chip */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="flex items-center gap-2 mb-8"
      >
        <span
          className="inline-flex rounded-full h-1.5 w-1.5 shrink-0"
          style={{
            background: "#22C55E",
            boxShadow: "0 0 6px 1px rgba(34,197,94,0.5)",
          }}
        />
        <span
          className="text-[11px] font-semibold tracking-[0.12em] uppercase"
          style={{ color: "#3A3735" }}
        >
          Norsk Tipping · Uke 26
        </span>
      </motion.div>

      {/* Barlow Condensed 900 — signature typographic moment */}
      <div style={{ lineHeight: 0.88, marginBottom: 28 }}>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
          style={{
            fontFamily: "var(--font-condensed)",
            fontWeight: 900,
            fontSize: "clamp(4.2rem, 11vw, 8.5rem)",
            color: "#FFFFFF",
            textTransform: "uppercase",
            letterSpacing: "-0.01em",
            display: "block",
          }}
        >
          Slå
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
          style={{
            fontFamily: "var(--font-condensed)",
            fontWeight: 900,
            fontSize: "clamp(4.2rem, 11vw, 8.5rem)",
            color: "#F5C030",
            textTransform: "uppercase",
            letterSpacing: "-0.01em",
            display: "block",
          }}
        >
          Folket.
        </motion.div>
      </div>

      {/* Description — deliberately muted, data does the talking */}
      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.45, delay: 0.32 }}
        className="text-[14px] leading-relaxed mb-9"
        style={{ color: "#4A4744", fontWeight: 400, maxWidth: 320 }}
      >
        Kupongoptimering for Tippekampen. Finn edge der modellen ser bedre verdi enn det folket tror.
      </motion.p>

      {/* CTAs */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4, delay: 0.44 }}
        className="flex items-center gap-3 flex-wrap"
      >
        <Link
          href="/coupon"
          className="inline-flex items-center gap-2 h-10 px-5 rounded-lg text-[13px] font-semibold transition-opacity hover:opacity-90"
          style={{ background: "#F5C030", color: "#0D0D0D" }}
        >
          Åpne kupong
          <ArrowRight size={13} strokeWidth={2.5} />
        </Link>
        <Link
          href="/coupon"
          className="inline-flex items-center h-10 px-5 rounded-lg text-[13px] font-medium"
          style={{
            border: "1px solid rgba(255,255,255,0.09)",
            color: "rgba(255,255,255,0.36)",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.62)";
            (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.16)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLElement).style.color = "rgba(255,255,255,0.36)";
            (e.currentTarget as HTMLElement).style.borderColor = "rgba(255,255,255,0.09)";
          }}
        >
          Kjør analyse
        </Link>
      </motion.div>
    </div>
  );
}

// ── Right panel: live match data ──────────────────────────────────────────────

function RightPanel() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.28 }}
      className="w-full rounded-xl overflow-hidden"
      style={{
        border: "1px solid rgba(255,255,255,0.07)",
        background: "#0B0B0E",
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
      >
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            <span
              className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-60"
              style={{ background: "#22C55E" }}
            />
            <span
              className="relative inline-flex rounded-full h-1.5 w-1.5"
              style={{ background: "#22C55E" }}
            />
          </span>
          <span
            className="text-[10px] font-semibold tracking-[0.1em] uppercase"
            style={{ color: "#333130", fontFamily: "var(--font-display)" }}
          >
            Live analyse · Uke 26
          </span>
        </div>
        <div className="flex items-center gap-5">
          {["Modell", "NT", "Edge"].map((label) => (
            <span
              key={label}
              className="text-[9px] tracking-widest uppercase"
              style={{ color: "#222020", fontFamily: "var(--font-mono)" }}
            >
              {label}
            </span>
          ))}
        </div>
      </div>

      {/* Match rows */}
      {MATCHES.map((m, i) => (
        <MatchRow key={i} m={m} index={i} />
      ))}

      {/* Footer */}
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{
          borderTop: "1px solid rgba(255,255,255,0.04)",
          background: "rgba(245,192,48,0.03)",
        }}
      >
        <span
          className="text-[10px]"
          style={{ fontFamily: "var(--font-mono)", color: "#2A2825" }}
        >
          Balanced · 192 kr · 192 rader
        </span>
        <Link
          href="/coupon"
          className="inline-flex items-center gap-1 text-[11px] font-semibold hover:opacity-80 transition-opacity"
          style={{ color: "#F5C030" }}
        >
          Se full kupong
          <ArrowRight size={10} />
        </Link>
      </div>
    </motion.div>
  );
}

// ── Export ────────────────────────────────────────────────────────────────────

export function TippeHero() {
  return (
    <div
      className="relative w-full"
      style={{ minHeight: "calc(100vh - 52px)", background: "#070709" }}
    >
      {/* Very faint gold ambient to frame the right panel */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 55% 65% at 82% 50%, rgba(245,192,48,0.04) 0%, transparent 60%)",
        }}
      />

      <div
        className="relative z-10 max-w-6xl mx-auto px-6"
        style={{ minHeight: "calc(100vh - 52px)", display: "flex", alignItems: "flex-start", paddingTop: "clamp(48px, 9vh, 96px)" }}
      >
        {/* Desktop two-column */}
        <div
          className="hidden lg:grid w-full gap-20 py-0"
          style={{ gridTemplateColumns: "42fr 58fr", alignItems: "center" }}
        >
          <LeftPanel />
          <RightPanel />
        </div>

        {/* Mobile stacked */}
        <div className="lg:hidden flex flex-col gap-10 py-12 w-full">
          <LeftPanel />
          <RightPanel />
        </div>
      </div>
    </div>
  );
}
