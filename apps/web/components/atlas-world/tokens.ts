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
  ink: "#12181F",
  parchment: "#E9E2CF",
  verdigris: "#3F6259",
  brass: "#B08D4F",
  signalAmber: "#E2A33B",
  threadCyan: "#4FB8AE",
} as const;

export type AtlasColor = keyof typeof ATLAS;
