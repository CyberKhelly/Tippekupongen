"use client";

import { cn } from "@/lib/utils";

// ─── Source: TippeQPongen_assets/08-dashboard.svg
//
// No modifications to colors, shapes, or the icon bars.
// Changes vs. the source card asset:
//   • "AI FOOTBALL ANALYTICS" subtitle removed from all renders.
//   • Outer card rect removed on light theme (bars + wordmark only).
//   • Wordmark repositioned from x=196 → x=148 for tight premium spacing.
//   • viewBox reframed to the live content ("62 65 258 53") for light theme.
//   • Card retained on dark theme because the bar/text fill (#0F0F10) is
//     invisible against dark surfaces — a proper dark SVG variant is needed.

const FONT = "Geist, Inter, 'Helvetica Neue', Arial, sans-serif";

// ── Shared: the five bar-chart bars + baseline ────────────────────────────────

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

// ── Light / stripped: no card, no subtitle ────────────────────────────────────
//
// viewBox "62 65 258 53":
//   x  62–320  →  4 px left of leftmost bar, ~21 px right of text end
//   y  65–118  →  4 px above cap-height, 4 px below icon baseline
//
// Wordmark at x=148: 22.5 unit gap after rightmost bar edge (x≈125.5),
// scales to ≈10 px at sm and ≈24 px at lg — Vercel / Linear territory.

function FullLight({ width, height }: { width: number; height: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 65 258 53"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <Bars />
      <text x="148" y="102"
            fontFamily={FONT} fontSize="46" letterSpacing="-1.5" fill="#0F0F10">
        <tspan fontWeight="500">Tippe</tspan><tspan fontWeight="700">IQ</tspan>
      </text>
    </svg>
  );
}

// ── Dark / card: card retained for contrast, subtitle removed ─────────────────
//
// The SVG elements use #0F0F10, which is invisible on dark surfaces.
// Until a dark-variant SVG is produced, the source card (fill #F8F6F1)
// provides necessary contrast.  Text kept at original x=196, y=92.

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
      <text x="196" y="92"
            fontFamily={FONT} fontSize="46" letterSpacing="-1.5" fill="#0F0F10">
        <tspan fontWeight="500">Tippe</tspan><tspan fontWeight="700">IQ</tspan>
      </text>
    </svg>
  );
}

// ── Icon only: bars cropped, no card ─────────────────────────────────────────
//
// viewBox "62 66 68 52":  x 62–130, y 66–118  (bars + baseline with 4 px margin)
// Natural aspect ratio 68:52 ≈ 1.31:1 — not forced square, matching the art.

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

// Icon for dark surfaces: keep the rounded card so bars are visible
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
//
// Full light — height drives width via viewBox 258:53 ratio (≈ 4.87:1)
//   sm  28 px → 136 px wide    md  40 px → 195 px    lg  56 px → 273 px
//
// Full dark — height drives width via source 600:180 ratio (≈ 3.33:1)
//   sm  32 px → 107 px wide    md  52 px → 173 px    lg  88 px → 293 px
//
// Icon — natural 68:52 ratio; size = height

const FULL_LIGHT_H = { sm: 28,  md: 40,  lg: 56  } as const;
const FULL_DARK_H  = { sm: 32,  md: 52,  lg: 88  } as const;
const ICON_H       = { sm: 22,  md: 30,  lg: 44  } as const;

// ── Component ─────────────────────────────────────────────────────────────────

export interface LogoProps {
  variant?: "full" | "icon";
  size?: "sm" | "md" | "lg";
  /**
   * "light" (default) — stripped logo, transparent bg, for off-white / white surfaces.
   * "dark"            — card logo, for dark surfaces (pending a proper dark SVG variant).
   */
  theme?: "light" | "dark";
  className?: string;
  /** Compat — unused */
  priority?: boolean;
}

export function Logo({ variant = "full", size = "md", theme = "light", className }: LogoProps) {
  if (variant === "icon") {
    return theme === "dark"
      ? <IconDark size={ICON_H[size]} />
      : <IconLight height={ICON_H[size]} />;
  }

  if (theme === "dark") {
    const h = FULL_DARK_H[size];
    const w = Math.round((h * 600) / 180);
    return (
      <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
        <FullDark width={w} height={h} />
      </div>
    );
  }

  const h = FULL_LIGHT_H[size];
  const w = Math.round((h * 258) / 53);
  return (
    <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
      <FullLight width={w} height={h} />
    </div>
  );
}

// Named export for NavRail (exact pixel height, always dark-surface variant)
export function LogoIcon({ height = 28, theme = "light" as "light" | "dark" } = {}) {
  return theme === "dark"
    ? <IconDark size={height} />
    : <IconLight height={height} />;
}
