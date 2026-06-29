"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getSignalBoard } from "@/lib/api";

// ── Custom SVG icons (exact paths from TippeNav.dc.html design reference) ────

function IconHome() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M2.5 6.8 8 2.3l5.5 4.5V13.5a.7.7 0 0 1-.7.7H9.6v-3.8H6.4v3.8H3.2a.7.7 0 0 1-.7-.7Z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
    </svg>
  );
}

function IconSignaler() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M1 8h3l1.8-4.5L9 12.5 10.8 8H15" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
    </svg>
  );
}

function IconKupong() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <rect x="2.2" y="3.2" width="11.6" height="9.6" rx="1.4" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M5.4 3.4v9.2" stroke="currentColor" strokeWidth="1.1" strokeDasharray="1.4 1.4"/>
    </svg>
  );
}

function IconModellspill() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="8.5" width="2.6" height="5" rx="0.6" fill="currentColor"/>
      <rect x="6.7" y="5.5" width="2.6" height="8" rx="0.6" fill="currentColor"/>
      <rect x="10.9" y="3" width="2.6" height="10.5" rx="0.6" fill="currentColor"/>
    </svg>
  );
}

function IconHistorikk() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <circle cx="8" cy="8" r="5.8" stroke="currentColor" strokeWidth="1.3"/>
      <path d="M8 4.8V8l2.3 1.6" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
    </svg>
  );
}

function IconSystemspill() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <rect x="2.5" y="2.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <rect x="9" y="2.5" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <rect x="2.5" y="9" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3"/>
      <rect x="9" y="9" width="4.5" height="4.5" rx="1" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  );
}

function IconInnstillinger() {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      <path d="M2 5h12M2 11h12" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="10" cy="5" r="2" fill="#0c0c0e" stroke="currentColor" strokeWidth="1.3"/>
      <circle cx="6" cy="11" r="2" fill="#0c0c0e" stroke="currentColor" strokeWidth="1.3"/>
    </svg>
  );
}

// ── Nav item ──────────────────────────────────────────────────────────────────

function NavItem({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string;
  icon: React.ComponentType;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      aria-label={label}
      aria-current={active ? "page" : undefined}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 11,
        padding: "9px 11px",
        borderRadius: 8,
        fontSize: 13.5,
        fontWeight: active ? 600 : 500,
        textDecoration: "none",
        color: active ? "#c9a04a" : "#86868c",
        background: active ? "rgba(201,160,74,0.10)" : "transparent",
        transition: "color 0.15s ease, background 0.15s ease",
        outline: "none",
        userSelect: "none",
      }}
      onMouseEnter={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.color = "#e4e4e6";
          (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          (e.currentTarget as HTMLElement).style.color = "#86868c";
          (e.currentTarget as HTMLElement).style.background = "transparent";
        }
      }}
    >
      <Icon />
      <span>{label}</span>
    </Link>
  );
}

// ── Section separator ─────────────────────────────────────────────────────────

function SectionLabel({ label }: { label: string }) {
  return (
    <div style={{ padding: "14px 10px 5px", display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.05)" }} />
      <span style={{
        fontSize: 9.5,
        fontWeight: 600,
        letterSpacing: "0.14em",
        textTransform: "uppercase" as const,
        color: "#54545a",
      }}>{label}</span>
      <span style={{ flex: 1, height: 1, background: "rgba(255,255,255,0.05)" }} />
    </div>
  );
}

// ── NavRail ───────────────────────────────────────────────────────────────────

export function NavRail() {
  const pathname = usePathname();

  const { data: signalBoard } = useQuery({
    queryKey: ["signal-board"],
    queryFn: () => getSignalBoard(),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const signalCount = signalBoard?.signals?.length ?? null;

  function isActive(href: string) {
    if (href === "/home") return pathname === "/home" || pathname === "/" || pathname === "";
    return pathname.startsWith(href);
  }

  return (
    <nav
      aria-label="Navigasjon"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        bottom: 0,
        width: 240,
        zIndex: 30,
        background: "#0c0c0e",
        borderRight: "1px solid rgba(255,255,255,0.06)",
        padding: "28px 16px 18px",
        display: "flex",
        flexDirection: "column",
        boxSizing: "border-box",
        fontFamily: "'Geist', -apple-system, 'Segoe UI', sans-serif",
      }}
    >
      {/* Logo */}
      <Link
        href="/home"
        aria-label="TippeIQ hjemmeside"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 11,
          padding: "0 10px 6px",
          textDecoration: "none",
          outline: "none",
        }}
      >
        <div
          style={{
            width: 18,
            height: 18,
            borderRadius: 5,
            background: "linear-gradient(140deg,#e4bd6a,#a87f31)",
            boxShadow: "0 0 16px rgba(201,160,74,0.45)",
            flexShrink: 0,
          }}
        />
        <span style={{ fontSize: 16, fontWeight: 600, letterSpacing: "-0.015em", color: "#f4f3f0" }}>
          Tippe<span style={{ color: "#c9a04a" }}>IQ</span>
        </span>
      </Link>

      {/* Nav items */}
      <div style={{ display: "flex", flexDirection: "column", gap: 2, marginTop: 30, flex: 1 }}>
        <NavItem href="/home" icon={IconHome} label="Oversikt" active={isActive("/home")} />

        <SectionLabel label="Kupong" />
        <NavItem href="/signaler" icon={IconSignaler} label="Signaler" active={isActive("/signaler")} />
        <NavItem href="/kupong" icon={IconKupong} label="Kupong" active={isActive("/kupong")} />

        <SectionLabel label="Odds" />
        <NavItem href="/oddstips" icon={IconModellspill} label="Modellspill" active={isActive("/oddstips")} />
        <NavItem href="/historikk" icon={IconHistorikk} label="Historikk" active={isActive("/historikk")} />

        <div style={{ marginTop: 8 }}>
          <NavItem href="/strategien" icon={IconSystemspill} label="Systemspill" active={isActive("/strategien")} />
          <NavItem href="/innstillinger" icon={IconInnstillinger} label="Innstillinger" active={isActive("/innstillinger")} />
        </div>
      </div>

      {/* Status footer */}
      <div
        style={{
          padding: "14px 10px 4px",
          borderTop: "1px solid rgba(255,255,255,0.05)",
          flexShrink: 0,
        }}
      >
        <div style={{
          fontSize: 9.5,
          fontWeight: 600,
          letterSpacing: "0.14em",
          textTransform: "uppercase",
          color: "#54545a",
          marginBottom: 8,
        }}>
          Modell status
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12.5, color: "#9a9a9f" }}>
          {/* Live pulse dot — uses tq-live-dot CSS class from globals.css */}
          <span className="tq-live-dot" aria-hidden="true" />
          {signalCount !== null ? `Aktiv · ${signalCount} signaler` : "Aktiv"}
        </div>
      </div>
    </nav>
  );
}
