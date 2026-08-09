"use client";

import { useMemo } from "react";

import { ATLAS, AtlasCanvas, TerrainField } from "@/components/atlas-world";
import type { ReliefCell } from "@/lib/types";

/**
 * The Dashboard Relief Map. Each document is a cell of a topographic height
 * grid: peak height = chunk mass scaled down by staleness, so large fresh docs
 * are mountains and stale/unverified docs sink into valleys. Real data only —
 * the grid is built from /dashboard/relief, never noise.
 *
 * Rendered via dynamic(ssr:false) from DashboardView so three.js is per-route.
 * Low-power / no-WebGL devices get the 2D bar fallback; the surrounding page
 * (recent docs, quick-ask) never depends on this rendering.
 */
export function ReliefMap({ cells }: { cells: ReliefCell[] }) {
  // Real height for a document: bigger = taller, staler = lower (valley).
  const heightOf = useMemo(() => {
    const maxMass = Math.max(1, ...cells.map((c) => c.mass));
    return (c: ReliefCell) => 0.12 + (c.mass / maxMass) * (1 - c.staleness) * 0.88;
  }, [cells]);

  // Lay documents onto an inner grid, padded with a low border so the relief
  // reads as an island rather than a spiky bar chart. TerrainField bilinearly
  // smooths between cells.
  const heights = useMemo(() => {
    const n = cells.length;
    if (n === 0) return [[0.1, 0.1], [0.1, 0.1]];
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);
    const G_ROWS = rows + 2;
    const G_COLS = cols + 2;
    const grid = Array.from({ length: G_ROWS }, () => Array<number>(G_COLS).fill(0.08));
    cells.forEach((c, i) => {
      const r = Math.floor(i / cols) + 1;
      const col = (i % cols) + 1;
      grid[r][col] = heightOf(c);
    });
    return grid;
  }, [cells, heightOf]);

  return (
    <AtlasCanvas
      camera={{ position: [0, 3.1, 5.4], fov: 46 }}
      fallback={<Relief2D cells={cells} heightOf={heightOf} />}
      render={({ reducedMotion }) => (
        <TerrainField
          heights={heights}
          size={5.5}
          relief={1.6}
          orbit
          contours
          reducedMotion={reducedMotion}
        />
      )}
    />
  );
}

/** 2D fallback: freshness bars. Same data, no WebGL. */
function Relief2D({
  cells,
  heightOf,
}: {
  cells: ReliefCell[];
  heightOf: (c: ReliefCell) => number;
}) {
  return (
    <div className="flex h-full w-full items-end justify-center gap-1.5 p-4">
      {cells.map((c) => {
        const h = Math.round(heightOf(c) * 100);
        // Verdigris (fresh) → brass (stale) so valleys read even without depth.
        const color = c.staleness > 0.5 ? ATLAS.brass : ATLAS.verdigris;
        return (
          <div
            key={c.id}
            title={`${c.filename} · ${c.mass} chunks · ${Math.round(c.staleness * 100)}% stale`}
            className="w-6 rounded-t-sm"
            style={{ height: `${h}%`, backgroundColor: color, opacity: 0.85 }}
          />
        );
      })}
    </div>
  );
}
