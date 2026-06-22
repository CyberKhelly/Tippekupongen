import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        gold:      "#D4930A",
        "gold-fill": "#F5C542",
        "gold-bg": "#FEF7E6",
        green:     "#15803D",
        red:       "#C42B2B",
        blue:      "#1D4ED8",
        base:      "#F5F3EF",
        surface:   "#FFFFFF",
        elevated:  "#FAF9F7",
        border:    "#E4E1DA",
        "border-subtle": "#EDE9E2",
        "text-1":  "#111110",
        "text-2":  "#6B6862",
        "text-3":  "#ADA9A2",
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
        sans:    ["var(--font-display)", "system-ui", "sans-serif"],
        mono:    ["ui-monospace", "SFMono-Regular", "monospace"],
        display: ["var(--font-display)", "system-ui", "sans-serif"],
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
