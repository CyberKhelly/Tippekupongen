"use client";

import { useState, useRef } from "react";

interface BudgetInputProps {
  value: number;
  onChange: (b: number) => void;
}

const QUICK: number[] = [96, 192, 384];

export function BudgetInput({ value, onChange }: BudgetInputProps) {
  const [draft, setDraft] = useState<string>("");
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function commit(raw: string) {
    const n = parseInt(raw, 10);
    if (!isNaN(n) && n >= 32) {
      onChange(Math.round(n / 32) * 32); // snap to multiples of 32 (minimum row cost)
    }
    setEditing(false);
    setDraft("");
  }

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {/* Input field */}
      <div
        onClick={() => { setEditing(true); setDraft(String(value)); setTimeout(() => inputRef.current?.select(), 0); }}
        style={{
          display: "flex", alignItems: "center", gap: 4,
          padding: "3px 8px 3px 10px",
          background: "#1A1A1A",
          border: "1px solid rgba(255,255,255,0.09)",
          borderRadius: 5,
          cursor: "text",
          minWidth: 72,
        }}
      >
        {editing ? (
          <input
            ref={inputRef}
            type="number"
            min={32}
            step={32}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={() => commit(draft)}
            onKeyDown={e => {
              if (e.key === "Enter") commit(draft);
              if (e.key === "Escape") { setEditing(false); setDraft(""); }
            }}
            autoFocus
            className="budget-input"
          />
        ) : (
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700,
            color: "#E8E4DD", fontVariantNumeric: "tabular-nums",
            letterSpacing: "0.02em",
            minWidth: 56, textAlign: "right",
          }}>
            {value}
          </span>
        )}
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#4A4744", flexShrink: 0 }}>
          kr
        </span>
      </div>

      {/* Quick-select chips */}
      <div style={{ display: "flex", gap: 3 }}>
        {QUICK.map(q => (
          <button
            key={q}
            onClick={() => onChange(q)}
            style={{
              padding: "3px 7px",
              borderRadius: 4,
              border: "1px solid",
              borderColor: value === q ? "var(--gold-border)" : "var(--bdr-1)",
              background: value === q ? "var(--gold-10)" : "transparent",
              fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600,
              color: value === q ? "var(--gold)" : "#4A4744",
              cursor: "pointer", transition: "all 0.12s",
              letterSpacing: "0.02em",
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

/* Legacy grid variant — kept for any external callers */
interface BudgetSelectorProps {
  budgets: number[];
  selected: number;
  onSelect: (b: number) => void;
  variant?: "horizontal" | "grid";
}

export function BudgetSelector({ budgets, selected, onSelect }: BudgetSelectorProps) {
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {budgets.map(b => {
        const isActive = b === selected;
        return (
          <button
            key={b}
            onClick={() => onSelect(b)}
            className="relative py-2.5 px-3 rounded-lg border text-left transition-colors duration-150 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--gold)]/30"
            style={{
              background: isActive ? "#1C1C1C" : "#141414",
              borderColor: isActive ? "rgba(245,192,48,0.3)" : "rgba(255,255,255,0.07)",
              color: isActive ? "#E8E4DD" : "#4A4744",
            }}
          >
            <div className="text-[13px] font-bold tabular-nums leading-none">{b} kr</div>
          </button>
        );
      })}
    </div>
  );
}
