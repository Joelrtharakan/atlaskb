import type { Config } from "tailwindcss";

/**
 * AtlasKB design tokens — see docs/design/frontend-design-plan.md.
 * Neutrals + one house metallic + two RESERVED state colors.
 * `beacon` and `meridian` must only ever appear for their reserved meaning.
 */
const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // --- Dark "night chart-table" palette (the canonical set) ---
        "chart-navy": "#0F1A24", // page background
        "deep-chart": "#16232F", // panel background
        parchment: "#E8E2D0", // primary text
        brass: "#C08A45", // primary accent, verified/elevated
        verdigris: "#4A7C6F", // secondary accent, ready state
        "signal-red": "#C1462F", // stale/alert state
        // --- Back-compat aliases: existing components reference these names, so
        // they are remapped to dark values and the whole app flips at once.
        ink: "#E8E2D0", // (was dark text) → now parchment (primary text on dark)
        linen: "#0F1A24", // (was light bg) → now chart-navy (page bg)
        graphite: "#8A99A0", // secondary text / hairlines, lightened for dark
        pewter: "#C08A45", // house accent → brass
        // RESERVED STATE COLORS.
        beacon: "#E8A22B", // "retrieval in progress / citations active"
        meridian: "#22B2A6", // "the 3D connection threads"
      },
      fontFamily: {
        // Wired to next/font CSS variables in app/layout.tsx
        display: ["var(--font-display)", "Times New Roman", "serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        cartouche: "0.22em", // wide-tracked map-title eyebrows
      },
    },
  },
  plugins: [],
};

export default config;
