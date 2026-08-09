/**
 * Northwind Survey design tokens for the 3D world. Kept in one place so every
 * atlas-world primitive draws from the same palette — the whole point of the
 * shared library is that all treatments read as one world, not twelve sketches.
 *
 * Colors mirror the CSS custom properties in globals.css / tailwind.config.ts.
 * Two are reserved and must not be used decoratively:
 *   - signalAmber: retrieval / active states only
 *   - threadCyan:  3D connection threads only
 */
export const ATLAS = {
  ink: "#0F1A24", // chart-navy (dark scene background)
  parchment: "#E8E2D0",
  verdigris: "#4A7C6F",
  brass: "#C08A45",
  signalAmber: "#E8A22B", // reserved: retrieval / active
  threadCyan: "#22B2A6", // reserved: 3D connection threads
} as const;

export type AtlasColor = keyof typeof ATLAS;
