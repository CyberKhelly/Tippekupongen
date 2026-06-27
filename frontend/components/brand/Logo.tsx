"use client";

import { cn } from "@/lib/utils";

// ─── Source: TippeQPongen_assets/08-dashboard.svg
//
// Typography refinements:
//   • Gap closed: wordmark x=148 → x=138 (≈6 px closer at sm, ≈9 px at lg)
//   • Weight unified: fontWeight 600 throughout (was 500/700 split)
//   • Gold reserved for icon only: wordmark is #0F0F10 throughout (Option A)
//   • Optical center: text y=102 → y=110 so both mark and wordmark share
//     visual center y≈93 (icon y=72–114, text cap y≈77–110)
//   • viewBox updated to "62 66 258 60" to match repositioned text

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

// ── Light / stripped ──────────────────────────────────────────────────────────
//
// Geometry:
//   Icon bars:  x=66–126, y=72–114 (floor line at 114), visual center y≈93
//   Wordmark:   baseline y=110, cap-top ≈y=77, visual center y≈93.5
//   → Icon and wordmark share the same optical vertical center. ✓
//
//   Gap (icon right ≈x=125.5 → text x=138) = 12.5 viewBox units
//   → ~7 px at sm (28 px), ~8 px at md (40 px), ~12 px at lg (56 px)
//
// viewBox "62 66 258 60"
//   y 66–126: 6 px margin above icon (72), 6 px below text descenders (~120)

function FullLight({ width, height }: { width: number; height: number }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg"
         viewBox="62 66 258 60"
         width={width} height={height}
         style={{ display: "block", flexShrink: 0 }}
         role="img" aria-label="TippeIQ">
      <Bars />
      <text
        x="138" y="110"
        fontFamily={FONT}
        fontSize="46"
        fontWeight="600"
        letterSpacing="-1.5"
        fill="#0F0F10"
      >
        TippeIQ
      </text>
    </svg>
  );
}

// ── Dark / card ───────────────────────────────────────────────────────────────
//
// Source card dimensions preserved (viewBox "0 0 600 180"). Subtitle removed.
// Weight updated to 600 for consistency with light variant.

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
      <text
        x="196" y="92"
        fontFamily={FONT}
        fontSize="46"
        fontWeight="600"
        letterSpacing="-1.5"
        fill="#0F0F10"
      >
        TippeIQ
      </text>
    </svg>
  );
}

// ── Icon only: bars, no card ──────────────────────────────────────────────────
//
// Natural aspect ratio 68:52 ≈ 1.31:1 (matches the art, not forced square)

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
// Full light — viewBox 258:60 → aspect ratio 4.3:1
//   sm  28 px → 121 px wide    md  40 px → 172 px    lg  56 px → 241 px
//
// Full dark — viewBox 600:180 → aspect ratio 3.33:1
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
  const w = Math.round((h * 258) / 60);
  return (
    <div className={cn("inline-flex flex-shrink-0 select-none", className)}>
      <FullLight width={w} height={h} />
    </div>
  );
}

export function LogoIcon({ height = 28, theme = "light" as "light" | "dark" } = {}) {
  return theme === "dark"
    ? <IconDark size={height} />
    : <IconLight height={height} />;
}
