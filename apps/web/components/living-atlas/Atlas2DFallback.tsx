"use client";

import { useMemo } from "react";

import type { AtlasEdge, AtlasNode } from "./layout";

// Lightweight 2D fallback for reduced-motion / low-power / no-WebGL. It renders
// the same layout as a flat survey map (no Three.js), still lighting retrieved
// and cited document nodes and drawing amber threads to the answer point. The
// citations panel remains fully functional alongside it.

const INK = "#16232B";
const GRAPHITE = "#515C63";
const BEACON = "#E8A22B";
const MERIDIAN = "#22B2A6";
const BRASS = "#C08A45";
const SIGNAL_RED = "#C1462F";

export interface Atlas2DProps {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  activeIds: string[];
  citedIds: string[];
  highlightedId: string | null;
  focus: boolean;
  reducedMotion: boolean;
  /** Document ids whose evidence is aging (staleness > 0.5) — tints the node
   * brass instead of the default teal, same threshold as the Dashboard relief
   * map and "Why this answer?" panel. */
  staleIds?: string[];
  /** Document id pairs currently flagged as factually conflicting for this
   * answer — drawn as a red link between the two nodes, with red rings on
   * both, so a disagreement is visible on the map itself, not just in text. */
  conflictPairs?: [string, string][];
}

export function Atlas2DFallback({
  nodes,
  edges,
  activeIds,
  citedIds,
  highlightedId,
  focus,
  reducedMotion,
  staleIds = [],
  conflictPairs = [],
}: Atlas2DProps) {
  const { view, project, center } = useMemo(() => {
    const xs = nodes.map((n) => n.position[0]);
    const ys = nodes.map((n) => n.position[1]);
    const pad = 1.5;
    const minX = Math.min(-1, ...xs) - pad;
    const maxX = Math.max(1, ...xs) + pad;
    const minY = Math.min(-1, ...ys) - pad;
    const maxY = Math.max(1, ...ys) + pad;
    const w = maxX - minX;
    const h = maxY - minY;
    // SVG y grows downward → flip.
    const project = (x: number, y: number): [number, number] => [x - minX, maxY - y];
    return {
      view: `0 0 ${w} ${h}`,
      project,
      center: project(0, 0),
    };
  }, [nodes]);

  const activeSet = useMemo(() => new Set(activeIds), [activeIds]);
  const citedSet = useMemo(() => new Set(citedIds), [citedIds]);
  const staleSet = useMemo(() => new Set(staleIds), [staleIds]);
  const conflictSet = useMemo(
    () => new Set(conflictPairs.flat()),
    [conflictPairs],
  );
  const showThreads = focus && activeIds.length > 0;

  return (
    <div className="relative h-full w-full">
      <svg
        viewBox={view}
        className="h-full w-full"
        role="img"
        aria-label="Document map (2D). Retrieved documents for the current answer are highlighted."
        preserveAspectRatio="xMidYMid meet"
      >
        {/* Latent structure. */}
        {edges.map((e, i) => {
          const [ax, ay] = project(nodes[e.a].position[0], nodes[e.a].position[1]);
          const [bx, by] = project(nodes[e.b].position[0], nodes[e.b].position[1]);
          return (
            <line key={`e${i}`} x1={ax} y1={ay} x2={bx} y2={by} stroke={GRAPHITE} strokeWidth={0.03} opacity={0.25} />
          );
        })}

        {/* Amber answer threads to the centre. */}
        {showThreads &&
          activeIds.map((id) => {
            const node = nodes.find((n) => n.id === id);
            if (!node) return null;
            const [ax, ay] = project(node.position[0], node.position[1]);
            return (
              <line
                key={`t${id}`}
                x1={ax}
                y1={ay}
                x2={center[0]}
                y2={center[1]}
                stroke={BEACON}
                strokeWidth={0.06}
                opacity={0.85}
                className={reducedMotion ? undefined : "atlas2d-draw"}
              />
            );
          })}

        {showThreads && (
          <circle cx={center[0]} cy={center[1]} r={0.28} fill={BEACON} opacity={0.95} />
        )}

        {/* Conflict links — two sources disagreeing, drawn directly between them. */}
        {conflictPairs.map(([aId, bId], i) => {
          const a = nodes.find((n) => n.id === aId);
          const b = nodes.find((n) => n.id === bId);
          if (!a || !b) return null;
          const [ax, ay] = project(a.position[0], a.position[1]);
          const [bx, by] = project(b.position[0], b.position[1]);
          return (
            <line
              key={`conflict-${i}`}
              x1={ax}
              y1={ay}
              x2={bx}
              y2={by}
              stroke={SIGNAL_RED}
              strokeWidth={0.08}
              strokeDasharray="0.12 0.12"
              opacity={0.9}
            />
          );
        })}

        {/* Document nodes. */}
        {nodes.map((n) => {
          const [x, y] = project(n.position[0], n.position[1]);
          const isActive = activeSet.has(n.id);
          const isCited = citedSet.has(n.id);
          const isHi = highlightedId === n.id;
          const isStale = staleSet.has(n.id);
          const isConflict = conflictSet.has(n.id);
          const r = (isHi ? 0.42 : isActive ? 0.3 : 0.2) * (0.8 + n.scale);
          const fill = isCited || isHi ? BEACON : isActive ? BEACON : isStale ? BRASS : MERIDIAN;
          return (
            <g key={n.id}>
              {isConflict && (
                <circle
                  cx={x}
                  cy={y}
                  r={r + 0.24}
                  fill="none"
                  stroke={SIGNAL_RED}
                  strokeWidth={0.07}
                  opacity={0.9}
                  className={reducedMotion ? undefined : "atlas2d-pulse"}
                />
              )}
              {isStale && (
                // Independent of fill color — staleness must stay visible even
                // when the node is also lit gold (active/cited), which the
                // fill color alone can't show since active/cited always wins
                // there. Smaller radius than the conflict ring so both can
                // show at once, nested.
                <circle
                  cx={x}
                  cy={y}
                  r={r + 0.12}
                  fill="none"
                  stroke={BRASS}
                  strokeWidth={0.06}
                  opacity={0.85}
                />
              )}
              {(isActive || isHi) && (
                <circle
                  cx={x}
                  cy={y}
                  r={r + 0.18}
                  fill="none"
                  stroke={BEACON}
                  strokeWidth={0.06}
                  opacity={isHi ? 1 : 0.8}
                  className={reducedMotion || !isActive ? undefined : "atlas2d-pulse"}
                />
              )}
              <circle cx={x} cy={y} r={r} fill={fill} opacity={isActive || isHi ? 0.95 : 0.55} />
              <circle cx={x} cy={y} r={r * 0.45} fill={INK} opacity={0.9} />
            </g>
          );
        })}
      </svg>

      <span className="marginalia pointer-events-none absolute left-3 top-3 text-[0.65rem] uppercase tracking-cartouche text-graphite">
        Atlas · 2D
      </span>
    </div>
  );
}
