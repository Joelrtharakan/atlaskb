"use client";

import { useMemo } from "react";

import {
  ATLAS,
  AtlasCanvas,
  ThreadField,
  type ThreadEdge,
  type ThreadNode,
} from "@/components/atlas-world";
import type { QueryVolumePoint } from "@/lib/types";

// "Trade winds": usage flowing across the atlas. The port network is a stable
// generated layout; what's real is the FLOW — particle density scales with total
// query volume and speed with the most recent day's volume. Particle-flow
// technique reused from the Living Atlas SignalPulses (via ThreadField), not a
// second particle system.

function portNetwork(): { nodes: ThreadNode[]; edges: ThreadEdge[] } {
  const N = 9;
  const nodes: ThreadNode[] = Array.from({ length: N }, (_, i) => {
    const seed = i * 97.13;
    const x = ((Math.sin(seed) + 1) / 2) * 8 - 4;
    const y = ((Math.cos(seed * 1.7) + 1) / 2) * 4 - 2;
    return { id: `port-${i}`, position: [x, y, 0] };
  });
  // Connect each port to its two nearest neighbors → trade routes.
  const edges: ThreadEdge[] = [];
  const seen = new Set<string>();
  nodes.forEach((n, i) => {
    const dists = nodes
      .map((m, j) => ({ j, d: (m.position[0] - n.position[0]) ** 2 + (m.position[1] - n.position[1]) ** 2 }))
      .filter((x) => x.j !== i)
      .sort((a, b) => a.d - b.d)
      .slice(0, 2);
    for (const { j } of dists) {
      const key = [Math.min(i, j), Math.max(i, j)].join("-");
      if (!seen.has(key)) {
        seen.add(key);
        edges.push({ a: i, b: j });
      }
    }
  });
  return { nodes, edges };
}

export function TradeWinds({ points }: { points: QueryVolumePoint[] }) {
  const { nodes, edges } = useMemo(portNetwork, []);
  const total = points.reduce((s, p) => s + p.count, 0);
  const recent = points.length ? points[points.length - 1].count : 0;

  // Real data → flow intensity. Busier weeks blow harder.
  const pulseCount = Math.max(6, Math.min(40, Math.round(total / 6)));
  const pulseSpeed = Math.max(0.5, Math.min(3, recent / 20));

  return (
    <AtlasCanvas
      camera={{ position: [0, 0, 9], fov: 45 }}
      fallback={<Winds2D total={total} />}
      render={({ reducedMotion }) => (
        <group>
          {/* ports */}
          {nodes.map((n) => (
            <mesh key={n.id} position={n.position}>
              <circleGeometry args={[0.07, 16]} />
              <meshBasicMaterial color={ATLAS.brass} />
            </mesh>
          ))}
          <ThreadField
            nodes={nodes}
            edges={edges}
            mode="flow"
            pulseCount={pulseCount}
            pulseSpeed={pulseSpeed}
            reducedMotion={reducedMotion}
          />
        </group>
      )}
    />
  );
}

function Winds2D({ total }: { total: number }) {
  return (
    <div className="flex h-full w-full items-center justify-center text-sm text-graphite">
      {total} queries flowing across the atlas
    </div>
  );
}
