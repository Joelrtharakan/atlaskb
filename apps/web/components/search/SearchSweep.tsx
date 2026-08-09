"use client";

import { useMemo } from "react";

import { AtlasCanvas, ThreadField, type ThreadNode } from "@/components/atlas-world";
import type { ScoredChunk } from "@/lib/types";

/**
 * The Search "compass sweep": the retrieved chunks laid out as a compact radial
 * field; a single radar arc rotates once and lights each result as it passes.
 * Deliberately quick and un-narrative (~1.2s) — "search is raw and fast" — versus
 * the Chat page's orchestrated camera move. Real data: the actual /search hits.
 *
 * Remount via a `key` on the parent to replay the sweep on each new query.
 */
export function SearchSweep({ results }: { results: ScoredChunk[] }) {
  const nodes = useMemo<ThreadNode[]>(() => {
    const n = Math.max(1, results.length);
    return results.map((c, i) => {
      // Rank spirals outward a little so higher hits sit nearer the center.
      const angle = (i / n) * Math.PI * 2;
      const r = 1.2 + (i / n) * 1.4;
      return { id: c.chunk_id, position: [Math.cos(angle) * r, Math.sin(angle) * r, 0] };
    });
  }, [results]);

  const matched = useMemo(() => results.map((c) => c.chunk_id), [results]);

  if (results.length === 0) return null;

  return (
    <AtlasCanvas
      camera={{ position: [0, 0, 6.5], fov: 45 }}
      fallback={null}
      render={({ reducedMotion }) => (
        <ThreadField
          nodes={nodes}
          mode="sweep"
          matchedIds={matched}
          reducedMotion={reducedMotion}
        />
      )}
    />
  );
}
