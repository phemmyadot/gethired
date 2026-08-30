import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink:     "#0F1923",
        surface: "#1C2B3A",
        panel:   "#253447",
        border:  "#2E4057",
        muted:   "#8B9EB7",
        teal:    "#00C2A8",
        amber:   "#F5A623",
        rose:    "#E8445A",
        sky:     "#4A9EE8",
        text:    "#D4E2F0",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
