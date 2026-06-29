"use client";

import { cn } from "@/lib/utils";

// ─── Source: TippeQPongen_assets/08-dashboard.svg
//
// Bar geometry (all values from SVG, baseline at y=114):
//   Bar 1: x=66.5  h=24  (57% of max)
//   Bar 2: x=79.5  h=15  (36%)
//   Bar 3: x=92.5  h=34  (81%)
//   Bar 4: x=105.5 h=21  (50%)
//   Bar 5: x=118.5 h=42  (100%, GOLD)
//   Spacing: 13px between bar starts, 7px wide each
//
// Wordmark: "Tippe" weight 500 + "IQ" weight 700, Geist, 46px, tracking -1.5

const FONT = "Geist, Inter, 'Helvetica Neue', Arial, sans-serif";

// ── Bars: original SVG (dark bars, for light surfaces) ────────────────────────
function Bars() {
  return (
    <>
      <line x1="66" y1="114" x2="126" y2="114"
            stroke="#0F0F10" strokeWidth="3" opacity="0.5" strokeLinecap="round" />
      <rect x="66.5"  y="90" width="7" height="24" rx="3" fill="#0F0F10" />
      <rect x="79.5"  y="99" width="7" height="15" rx="3" fill="#0F0F10" />
      <rect x="92.5"  y="80" width="7" height="34" rx="3" fill="#0F0F10" />
      <rect x="105.5" y="93" width="7" height="21" rx="3" fill="#0F0F10" />
      <rect x="118.5" y="72" width="7" height="42" rx="3" fill="#F5C542" />
    </>
  );
}

// ── Bars: adapted for dark surfaces (light bars + gold) ───────────────────────
function BarsOnDark() {
  return (
    <>
      <line x1="66" y1="114" x2="126" y2="114"
            stroke="rgba(255,255,255,0.16)" strokeWidth="3" strokeLinecap="round" />
      <rect x="66.5"  y="90" width="7" height="24" rx="3" fill="rgba(255,255,255,0.30)" />
      <rect x="79.5"  y="99" width="7" height="15" rx="3" fill="rgba(255,255,255,0.30)" />
      <rect x="92.5"  y="80" width="7" height="34" rx="3" fill="rgba(255,255,255,0.30)" />
      <rect x="105.5" y="93" width="7" height="21" rx="3" fill="rgba(255,255,255,0.30)" />
      <rect x="118.5" y="72" width="7" height="42" rx="3" fill="#F5C542" />
    </>
  );
}

// ── Full wordmark: light surface ──────────────────────────────────────────────
function FullLight({ width, height }: { width: number; height: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 66 258 60"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <Bars />
      <text x="138" y="110" fontFamily={FONT} fontSize="46" letterSpacing="-1.5" fill="#0F0F10">
        <tspan fontWeight="500">Tippe</tspan><tspan fontWeight="700">IQ</tspan>
      </text>
    </svg>
  );
}

// ── Full wordmark: dark surface ───────────────────────────────────────────────
function FullOnDark({ width, height }: { width: number; height: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 66 258 60"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <BarsOnDark />
      <text x="138" y="110" fontFamily={FONT} fontSize="46" letterSpacing="-1.5" fill="#E8E4DD">
        <tspan fontWeight="500">Tippe</tspan><tspan fontWeight="700" fill="#F5C542">IQ</tspan>
      </text>
    </svg>
  );
}

// ── Card (original light bg, for embeds / light context) ─────────────────────
function FullDark({ width, height }: { width: number; height: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="0 0 600 180"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <rect x="0.5" y="0.5" width="599" height="179" rx="26" fill="#F8F6F1" stroke="#E7E3D9" />
      <rect x="40"  y="34"  width="112" height="112" rx="26" fill="#F8F6F1" stroke="#E7E3D9" />
      <Bars />
      <text x="196" y="92" fontFamily={FONT} fontSize="46" letterSpacing="-1.5" fill="#0F0F10">
        <tspan fontWeight="500">Tippe</tspan><tspan fontWeight="700">IQ</tspan>
      </text>
    </svg>
  );
}

// ── Icon only: light surface ──────────────────────────────────────────────────
function IconLight({ height }: { height: number }) {
  const width = Math.round(height * (68 / 52));
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 66 68 52"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <Bars />
    </svg>
  );
}

// ── Icon only: dark surface (NavRail, dark panels) ────────────────────────────
function IconOnDark({ size }: { size: number }) {
  const width = Math.round(size * (68 / 52));
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 66 68 52"
         width={width} height={size}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <BarsOnDark />
    </svg>
  );
}

// ── Icon only: original card (kept for compat) ────────────────────────────────
function IconDark({ size }: { size: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="37 31 118 118"
         width={size} height={size}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <rect x="40" y="34" width="112" height="112" rx="26" fill="#F8F6F1" stroke="#E7E3D9" />
      <Bars />
    </svg>
  );
}

// ── Size tokens ───────────────────────────────────────────────────────────────
const FULL_H = { sm: 28, md: 40, lg: 56 } as const;
const ICON_H = { sm: 22, md: 30, lg: 44 } as const;

// ── Logo component ────────────────────────────────────────────────────────────
export interface LogoProps {
  variant?: "full" | "icon";
  size?: "sm" | "md" | "lg";
  /** "light" — light surface. "dark" — original card. "on-dark" — adapted for dark surfaces. */
  theme?: "light" | "dark" | "on-dark";
  className?: string;
  priority?: boolean;
}

export function Logo({ variant = "full", size = "md", theme = "light", className }: LogoProps) {
  if (variant === "icon") {
    const h = ICON_H[size];
    if (theme === "on-dark") return <IconOnDark size={h} />;
    if (theme === "dark")    return <IconDark size={h} />;
    return <IconLight height={h} />;
  }

  const h = FULL_H[size];
  const w = Math.round(h * (258 / 60));

  if (theme === "on-dark") {
    return (
      <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
        <FullOnDark width={w} height={h} />
      </div>
    );
  }
  if (theme === "dark") {
    const dh = { sm: 32, md: 52, lg: 88 }[size] ?? 52;
    const dw = Math.round((dh * 600) / 180);
    return (
      <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
        <FullDark width={dw} height={dh} />
      </div>
    );
  }
  return (
    <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
      <FullLight width={w} height={h} />
    </div>
  );
}

// ── LogoIcon shorthand ────────────────────────────────────────────────────────
export function LogoIcon({
  height = 28,
  theme = "light" as "light" | "dark" | "on-dark",
} = {}) {
  if (theme === "on-dark") return <IconOnDark size={height} />;
  if (theme === "dark")    return <IconDark size={height} />;
  return <IconLight height={height} />;
}
