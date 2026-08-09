"use client";

import { useMemo } from "react";

import {
  ATLAS,
  AtlasCanvas,
  type CoreLayer,
  CoreSampleStack,
} from "@/components/atlas-world";
import type { ChunkSample } from "@/lib/types";

/** Interpolate two #rrggbb colors. */
function hexLerp(a: string, b: string, t: number): string {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const c = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.max(0, Math.min(1, t))));
  return `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

/** Color a stratum: low confidence → brass, high confidence → verdigris. */
export function colorForChunk(c: ChunkSample): string {
  return hexLerp(ATLAS.brass, ATLAS.verdigris, c.confidence);
}

/**
 * The document's chunks as a geological core sample: layer thickness ∝ chunk
 * length, color = embedding centrality (representative chunks read as solid
 * verdigris; outliers/boilerplate as pale brass). Hover fires onHover(chunk_id)
 * so the page shows that chunk's text. Real data from /documents/{id}/chunks.
 */
export function CoreSample({
  layers,
  hoveredId,
  onHover,
}: {
  layers: ChunkSample[];
  hoveredId: string | null;
  onHover: (id: string | null) => void;
}) {
  const coreLayers = useMemo<CoreLayer[]>(
    () =>
      layers.map((l) => ({
        id: l.chunk_id,
        thickness: l.length,
        color: colorForChunk(l),
      })),
    [layers],
  );

  return (
    <AtlasCanvas
      camera={{ position: [2.6, 0.6, 4.4], fov: 42 }}
      fallback={<Core2D layers={layers} hoveredId={hoveredId} onHover={onHover} />}
      render={({ reducedMotion }) => (
        <CoreSampleStack
          layers={coreLayers}
          hoveredId={hoveredId}
          onHover={onHover}
          height={4.4}
          radius={0.85}
          reducedMotion={reducedMotion}
        />
      )}
    />
  );
}

/** 2D fallback: stacked strata as horizontal bands. */
function Core2D({
  layers,
  hoveredId,
  onHover,
}: {
  layers: ChunkSample[];
  hoveredId: string | null;
  onHover: (id: string | null) => void;
}) {
  const total = layers.reduce((s, l) => s + l.length, 0) || 1;
  return (
    <div className="flex h-full w-full flex-col justify-center gap-0.5 p-4">
      {layers.map((l) => (
        <div
          key={l.chunk_id}
          onMouseEnter={() => onHover(l.chunk_id)}
          onMouseLeave={() => onHover(null)}
          className="w-full rounded-sm transition-transform"
          style={{
            height: `${Math.max(4, (l.length / total) * 100)}%`,
            backgroundColor: colorForChunk(l),
            outline: hoveredId === l.chunk_id ? "2px solid var(--pewter, #8793A0)" : "none",
          }}
        />
      ))}
    </div>
  );
}
