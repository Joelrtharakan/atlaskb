"use client";

import { useMemo } from "react";

import { AtlasCanvas, TerrainField } from "@/components/atlas-world";

// The landing hero's right-side visual: a real heightmap terrain (same
// "elevation = document scale/freshness" concept as the dashboard) — brass peaks,
// verdigris valleys, emissive brass contour wireframe. Ties the marketing page to
// the product instead of a generic AI network graph. No teal anywhere.
function heroRelief(): number[][] {
  const G = 13;
  const grid: number[][] = [];
  for (let r = 0; r < G; r++) {
    const row: number[] = [];
    for (let c = 0; c < G; c++) {
      const x = c / (G - 1) - 0.5;
      const y = r / (G - 1) - 0.5;
      // A dominant peak, a secondary shoulder, and a low ridge — a real massif.
      const d1 = Math.hypot(x - 0.04, y - 0.02);
      const d2 = Math.hypot(x + 0.3, y + 0.24);
      const h =
        Math.exp(-(d1 * d1) / 0.05) * 0.98 +
        Math.exp(-(d2 * d2) / 0.02) * 0.42 +
        0.1 * Math.sin((x + y) * 6.2);
      row.push(Math.max(0.05, Math.min(1, h)));
    }
    grid.push(row);
  }
  return grid;
}

export function HeroTerrain() {
  const heights = useMemo(heroRelief, []);
  return (
    <AtlasCanvas
      camera={{ position: [0, 4.4, 6.6], fov: 40 }}
      fallback={null}
      render={({ reducedMotion }) => (
        <TerrainField
          heights={heights}
          size={6}
          relief={1.9}
          orbit
          contours
          reducedMotion={reducedMotion}
        />
      )}
    />
  );
}
