import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtPct(v: number, decimals = 2): string {
  return `${(v * 100).toFixed(decimals)}%`;
}

export function fmtPvr(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}×`;
}

export function fmtKr(v: number): string {
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M kr`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k kr`;
  return `${Math.round(v)} kr`;
}

/** Short label for a coupon day_type or key. */
export function couponLabel(couponId: string): string {
  if (couponId.startsWith("midtuke")) return "Midtuke";
  if (couponId.startsWith("lordag")) return "Lørdag";
  if (couponId.startsWith("sondag")) return "Søndag";
  return couponId;
}

/** Relative time label: "2 min siden", "1 t siden", "Aldri". */
export function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "Aldri";
  const diffMs = Date.now() - new Date(iso).getTime();
  const secs = Math.floor(diffMs / 1000);
  if (secs < 60) return "Akkurat nå";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} min siden`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} t siden`;
  return `${Math.floor(hrs / 24)} d siden`;
}

/** "om 3 min", "om 1 t" — for upcoming timestamps. */
export function formatUntil(iso: string | null | undefined): string {
  if (!iso) return "—";
  const secs = Math.floor((new Date(iso).getTime() - Date.now()) / 1000);
  if (secs <= 0) return "Nå";
  if (secs < 60) return `om ${secs}s`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `om ${mins} min`;
  const hrs = Math.floor(mins / 60);
  return `om ${hrs} t`;
}

/** Seconds until ISO datetime (negative if in the past). */
export function secsUntil(iso: string | null | undefined): number {
  if (!iso) return Infinity;
  return (new Date(iso).getTime() - Date.now()) / 1000;
}

/**
 * Returns true if this league uses group-stage standings where a position
 * number is not a reliable single-table rank (e.g. World Cup groups of 4).
 * Position is hidden in the UI for these leagues to avoid misleading the user.
 */
export function isGroupStageTournament(leagueName: string | null | undefined): boolean {
  if (!leagueName) return false;
  const lc = leagueName.toLowerCase();
  return lc.includes("world cup") || lc.includes("champions league") || lc.includes("nations league");
}

/** Value (edge) for the recommended pick. */
export function recValue(
  rec: string,
  value_h: number | null,
  value_u: number | null,
  value_b: number | null
): number | null {
  return { H: value_h, U: value_u, B: value_b }[rec] ?? null;
}
