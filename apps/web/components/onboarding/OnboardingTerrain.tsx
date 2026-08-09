"use client";

import { useMemo } from "react";

import {
  AtlasCanvas,
  TerrainField,
  type TerrainMarker,
} from "@/components/atlas-world";

// A gentle relief. On a *new* workspace there is genuinely no document data yet,
// so this represents the landscape about to be filled — it animates up from flat
// (autoForm). On *join*, the terrain is already formed with a marker at "your"
// position. Deterministic (not random) so it's stable between renders.
function gentleRelief(): number[][] {
  const G = 9;
  const grid: number[][] = [];
  for (let r = 0; r < G; r++) {
    const row: number[] = [];
    for (let c = 0; c < G; c++) {
      const u = c / (G - 1) - 0.5;
      const v = r / (G - 1) - 0.5;
      const h =
        0.5 +
        0.35 * Math.cos(u * 3.1) * Math.cos(v * 2.7) +
        0.15 * Math.sin((u + v) * 4.0);
      row.push(Math.max(0.05, Math.min(1, h)));
    }
    grid.push(row);
  }
  return grid;
}

export function OnboardingTerrain({ joining }: { joining: boolean }) {
  const heights = useMemo(() => gentleRelief(), []);
  const markers = useMemo<TerrainMarker[]>(
    () => (joining ? [{ x: 0.62, z: 0.42, color: "#B08D4F" }] : []),
    [joining],
  );

  return (
    <AtlasCanvas
      camera={{ position: [0, 4, 6.5], fov: 42 }}
      fallback={null}
      render={({ reducedMotion }) => (
        <TerrainField
          heights={heights}
          size={6}
          relief={1.6}
          // New workspace: form up from flat. Joining: already formed.
          autoForm={!joining}
          markers={markers}
          reducedMotion={reducedMotion}
        />
      )}
    />
  );
}
