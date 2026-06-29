"use client";

import { motion } from "framer-motion";
import { Users, BarChart2, Brain, Ticket, type LucideIcon } from "lucide-react";

const EASE = [0.16, 1, 0.3, 1] as const;

interface CardData {
  label: string;
  sub: string;
  Icon: LucideIcon;
  emphasized?: boolean;
}

const FLOW_CARDS: CardData[] = [
  { label: "Folket",  sub: "Hva tror folk?",      Icon: Users      },
  { label: "Odds",    sub: "Hva sier markedet?",  Icon: BarChart2  },
  { label: "Modell",  sub: "Hva sier modellen?",  Icon: Brain,     emphasized: true },
  { label: "Kupong",  sub: "Vår anbefaling",       Icon: Ticket     },
];

function FlowCard({ data, index }: { data: CardData; index: number }) {
  const { label, sub, Icon, emphasized } = data;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: emphasized ? -12 : 0 }}
      transition={{ delay: 0.08 + index * 0.09, duration: 0.55, ease: EASE }}
      style={{
        width: emphasized ? 146 : 118,
        flexShrink: 0,
        padding: emphasized ? "22px 14px 20px" : "18px 12px 16px",
        borderRadius: 16,
        background: "#FFFFFF",
        border: emphasized
          ? "1.5px solid rgba(245,197,66,0.48)"
          : "1px solid rgba(15,15,16,0.08)",
        boxShadow: emphasized
          ? "0 16px 48px rgba(245,197,66,0.13), 0 4px 12px rgba(0,0,0,0.06)"
          : "0 1px 4px rgba(0,0,0,0.05)",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
        textAlign: "center",
      }}
    >
      <div
        style={{
          width: 38,
          height: 38,
          borderRadius: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: emphasized ? "rgba(245,197,66,0.12)" : "rgba(15,15,16,0.04)",
          flexShrink: 0,
        }}
      >
        <Icon size={17} strokeWidth={1.75} color={emphasized ? "#DFAF2B" : "#9CA3AF"} />
      </div>
      <div>
        <div
          style={{
            fontFamily: "var(--font-heading)",
            fontWeight: emphasized ? 700 : 500,
            fontSize: emphasized ? 14 : 13,
            color: emphasized ? "#0F0F10" : "#374151",
            letterSpacing: "-0.02em",
            lineHeight: 1.2,
          }}
        >
          {label}
        </div>
        <div
          style={{
            fontFamily: "var(--font-sans)",
            fontSize: 10.5,
            color: "#9CA3AF",
            marginTop: 3,
            lineHeight: 1.3,
          }}
        >
          {sub}
        </div>
      </div>
    </motion.div>
  );
}

export function HomeFlowVisual() {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: 12,
        width: "100%",
        maxWidth: 560,
        margin: "0 auto",
      }}
    >
      {FLOW_CARDS.map((card, i) => (
        <FlowCard key={card.label} data={card} index={i} />
      ))}
    </div>
  );
}
