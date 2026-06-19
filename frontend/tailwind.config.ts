import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        gold: "#f5c518",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        mono: ["var(--font-inter)", "ui-monospace", "monospace"],
      },
      backgroundImage: {
        "page-gradient":
          "radial-gradient(ellipse at 18% 0%, rgba(18,50,120,0.45) 0%, transparent 55%), radial-gradient(ellipse at 85% 95%, rgba(10,25,70,0.25) 0%, transparent 50%)",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        barGrow: {
          "0%": { transform: "scaleX(0)" },
          "100%": { transform: "scaleX(1)" },
        },
        shimmerSlide: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        glowPulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.25" },
        },
        scaleIn: {
          "0%": { opacity: "0", transform: "scale(0.94)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
      },
      animation: {
        "fade-up": "fadeUp 0.35s ease-out both",
        "bar-grow": "barGrow 0.65s cubic-bezier(0.16, 1, 0.3, 1) both",
        shimmer: "shimmerSlide 1.6s linear infinite",
        "glow-pulse": "glowPulse 2s ease-in-out infinite",
        "scale-in": "scaleIn 0.25s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
