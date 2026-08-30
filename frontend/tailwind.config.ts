import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // Warm off-white surfaces, ink text, single confident accent
        paper:   "#FAF7F2",
        surface: "#FFFFFF",
        panel:   "#F3EEE6",
        border:  "#E7E0D4",
        ink:     "#1C1A17",
        muted:   "#8A8378",
        accent:  "#5B4CFF",
        "accent-soft": "#EFECFF",
        teal:    "#1A8A72",
        "teal-soft": "#E4F3EE",
        amber:   "#B8720A",
        "amber-soft": "#FBF0DD",
        rose:    "#C23B4C",
        "rose-soft": "#FBEAEC",
        sky:     "#2A6FB0",
        "sky-soft": "#E9F1FA",
      },
      fontFamily: {
        display: ["'Fraunces'", "Georgia", "serif"],
        sans: ["'Public Sans'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(28,26,23,0.04), 0 8px 24px -12px rgba(28,26,23,0.12)",
        "card-hover": "0 2px 4px rgba(28,26,23,0.06), 0 16px 32px -12px rgba(28,26,23,0.18)",
      },
      borderRadius: {
        xl2: "1.25rem",
      },
    },
  },
  plugins: [],
};

export default config;
