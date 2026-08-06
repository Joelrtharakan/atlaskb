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
        // Neutrals
        ink: "#16232B", // primary text, strokes, node cores
        linen: "#D9DCD1", // app background — cool sage-linen (NOT cream)
        graphite: "#515C63", // secondary text, hairline neatlines, latent threads
        // House metallic (the only interactive accent)
        pewter: "#8793A0",
        // RESERVED STATE COLORS — do not use for anything else.
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
