import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        // Console design system
        canvas: "#0b0c0e",
        panel: "#101216",
        raised: "#16191e",
        well: "#0f1114",
        signal: "#4da3ff",
        confirm: "#3fbf88",
        attention: "#e0a24a",
        text: "#f2f4f7",
        stem: {
          vocals: "#c56edc",
          drums: "#4da3ff",
          bass: "#3fbf88",
          other: "#e0a24a",
          guitar: "#e8607a",
          piano: "#6ee7d0",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
