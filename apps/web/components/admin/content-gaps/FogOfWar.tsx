"use client";

import { useMemo } from "react";

import {
  AtlasCanvas,
  FogLayer,
  type FogPatch,
  TerrainField,
} from "@/components/atlas-world";
import type { ContentGap, ReliefCell } from "@/lib/types";

// Reuses the Dashboard's relief terrain and drapes shader fog over it. Each
// unresolved content-gap cluster is a fog patch; resolving one eases its
// intensity to 0 and the fog visibly clears (~1.5s, handled inside FogLayer).

function heightGrid(cells: ReliefCell[]): number[][] {
  if (cells.length === 0) return [[0.1, 0.1], [0.1, 0.1]];
  const maxMass = Math.max(1, ...cells.map((c) => c.mass));
  const cols = Math.ceil(Math.sqrt(cells.length));
  const rows = Math.ceil(cells.length / cols);
  const grid = Array.from({ length: rows + 2 }, () => Array<number>(cols + 2).fill(0.08));
  cells.forEach((c, i) => {
    grid[Math.floor(i / cols) + 1][(i % cols) + 1] =
      0.12 + (c.mass / maxMass) * (1 - c.staleness) * 0.88;
  });
  return grid;
}

export function FogOfWar({ cells, gaps }: { cells: ReliefCell[]; gaps: ContentGap[] }) {
  const heights = useMemo(() => heightGrid(cells), [cells]);

  // A patch per gap. Resolved → target intensity 0 so FogLayer eases it clear.
  const patches = useMemo<FogPatch[]>(
    () =>
      gaps.map((g) => ({
        id: g.key,
        x: g.x,
        y: g.y,
        radius: g.radius,
        intensity: g.resolved ? 0 : Math.min(0.92, 0.5 + g.count * 0.12),
      })),
    [gaps],
  );

  return (
    <AtlasCanvas
      camera={{ position: [0, 5.6, 6.4], fov: 44 }}
      fallback={<Fog2D gaps={gaps} />}
      render={({ reducedMotion }) => (
        <group>
          <TerrainField
            heights={heights}
            size={6}
            relief={1.4}
            reducedMotion={reducedMotion}
          />
          <FogLayer patches={patches} size={6} y={1.5} reducedMotion={reducedMotion} />
        </group>
      )}
    />
  );
}

/** 2D fallback: gaps as a fogged list, cleared ones struck through. */
function Fog2D({ gaps }: { gaps: ContentGap[] }) {
  return (
    <ul className="flex h-full w-full flex-col justify-center gap-1 p-4 text-sm">
      {gaps.map((g) => (
        <li
          key={g.key}
          className={g.resolved ? "text-graphite line-through" : "text-ink"}
          style={{ opacity: g.resolved ? 0.5 : 0.6 + Math.min(0.4, g.count * 0.1) }}
        >
          {g.query} · {g.count}×
        </li>
      ))}
    </ul>
  );
}
