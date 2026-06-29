import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        gold:        "#C9A04A",
        "gold-hover":"#DCB35F",
        "gold-fill": "#C9A04A",
        "gold-bg":   "rgba(201,160,74,0.10)",
        "gold-22":   "rgba(201,160,74,0.22)",
        green:       "#5FAE6E",
        "green-12":  "rgba(95,174,110,0.12)",
        red:         "#C8554E",
        "red-14":    "rgba(200,85,78,0.14)",
        blue:        "#6098F2",
        base:        "#0A0A0B",
        "surf-0":    "#0C0C0E",
        surface:     "#0E0E10",
        elevated:    "#16161A",
        "surf-3":    "#1F1F24",
        border:      "rgba(255,255,255,0.06)",
        "border-subtle": "rgba(255,255,255,0.04)",
        "border-mid":"rgba(255,255,255,0.12)",
        "text-1":    "#F4F3F0",
        "text-2":    "#9A9A9F",
        "text-3":    "#65656B",
        "text-4":    "#54545A",
        "text-dim":  "#86868C",
        // Light theme tokens (kept for any remaining light-theme pages)
        lbg:     "#F8F6F1",
        lcard:   "#FFFFFF",
        ltxt:    "#0F0F10",
        ltxt2:   "#6B7280",
        ltxt3:   "#9CA3AF",
        lyellow: "#F5C542",
        lgold:   "#DFAF2B",
        lpos:    "#16A34A",
        lneg:    "#EF4444",
        linfo:   "#3B82F6",
        sidebar: {
          DEFAULT:            "hsl(var(--sidebar-background))",
          foreground:         "hsl(var(--sidebar-foreground))",
          primary:            "hsl(var(--sidebar-primary))",
          "primary-foreground": "hsl(var(--sidebar-primary-foreground))",
          accent:             "hsl(var(--sidebar-accent))",
          "accent-foreground": "hsl(var(--sidebar-accent-foreground))",
          border:             "hsl(var(--sidebar-border))",
          ring:               "hsl(var(--sidebar-ring))",
        },
      },
      fontFamily: {
        sans:    ["var(--font-sans)", "system-ui", "-apple-system", "sans-serif"],
        serif:   ["var(--font-serif)", "Georgia", "serif"],
        mono:    ["ui-monospace", "SFMono-Regular", "monospace"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        heading: ["var(--font-heading)", "var(--font-display)", "system-ui", "sans-serif"],
      },
      fontSize: {
        // semantic scale — use these instead of arbitrary px values
        "meta":    ["11px", { lineHeight: "1.45", letterSpacing: "0.01em"  }],
        "label":   ["12px", { lineHeight: "1.4",  letterSpacing: "0em"    }],
        "body":    ["14px", { lineHeight: "1.5",  letterSpacing: "-0.01em"}],
        "body-lg": ["16px", { lineHeight: "1.55", letterSpacing: "-0.01em"}],
        "title":   ["18px", { lineHeight: "1.3",  letterSpacing: "-0.02em"}],
        "section": ["24px", { lineHeight: "1.2",  letterSpacing: "-0.025em"}],
        "page":    ["36px", { lineHeight: "1.15", letterSpacing: "-0.03em"}],
      },
      letterSpacing: {
        display: "-0.03em",
        heading: "-0.025em",
        ui:      "-0.01em",
        normal:  "0em",
        wide:    "0.05em",
        widest:  "0.1em",
      },
      lineHeight: {
        display: "1.05",
        heading: "1.2",
        snug:    "1.35",
        body:    "1.5",
        relaxed: "1.65",
      },
      keyframes: {
        fadeUp: {
          "0%":   { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        barGrow: {
          "0%":   { transform: "scaleX(0)" },
          "100%": { transform: "scaleX(1)" },
        },
        shimmerSlide: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        scaleIn: {
          "0%":   { opacity: "0", transform: "scale(0.94)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-up":  "fadeUp 0.35s ease-out both",
        "bar-grow": "barGrow 0.65s cubic-bezier(0.16, 1, 0.3, 1) both",
        shimmer:    "shimmerSlide 1.6s linear infinite",
        "scale-in": "scaleIn 0.25s ease-out both",
      },
      boxShadow: {
        card:     "0 1px 3px rgba(0,0,0,0.05), 0 1px 2px rgba(0,0,0,0.03)",
        elevated: "0 4px 12px rgba(0,0,0,0.07), 0 1px 3px rgba(0,0,0,0.04)",
        input:    "inset 0 1px 2px rgba(0,0,0,0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
