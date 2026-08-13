"use client";

import { useState } from "react";

import type { Landmark } from "@/lib/how-it-works-content";

const BRASS = "#C08A45";
const VERDIGRIS = "#4A7C6F";
const GRAPHITE = "#8A99A0";
const PARCHMENT = "#E8E2D0";

interface NodeSpec {
  id: string;
  x: number;
  y: number;
}

// Hand-placed layout, three rows, every connector strictly horizontal or
// vertical — deliberately avoiding the diagonal-crossing layout this
// replaced, where two edges crossed directly on top of the node labels and
// each other. Request path on row 1 (camp → gate → tower → peaks); cache +
// vault sit directly under the stop that calls them (row 2) so the
// connector is a short straight drop, not a line hunting across the
// diagram; ingestion feeds the vault from row 3.
const NODES: NodeSpec[] = [
  { id: "camp", x: 70, y: 50 },
  { id: "gate", x: 300, y: 50 },
  { id: "tower", x: 530, y: 50 },
  { id: "peaks", x: 760, y: 50 },
  { id: "signal-fire", x: 300, y: 210 },
  { id: "vault", x: 530, y: 210 },
  { id: "survey-team", x: 530, y: 340 },
];

interface EdgeSpec {
  from: string;
  to: string;
  kind: "primary" | "secondary" | "dashed";
  label?: string;
}

const EDGES: EdgeSpec[] = [
  { from: "camp", to: "gate", kind: "primary", label: "request" },
  { from: "gate", to: "tower", kind: "primary", label: "authorized" },
  { from: "tower", to: "peaks", kind: "dashed", label: "generate" },
  { from: "gate", to: "signal-fire", kind: "secondary", label: "cache check" },
  { from: "tower", to: "vault", kind: "primary", label: "hybrid search" },
  { from: "survey-team", to: "vault", kind: "secondary", label: "ingest write" },
];

function node(id: string): NodeSpec {
  return NODES.find((n) => n.id === id)!;
}

/** Trims a connector so it runs in the clear gap between two nodes' label
 * blocks (title above, subtitle below) instead of center-to-center, which
 * would draw the line straight through both nodes' text. */
function connector(a: NodeSpec, b: NodeSpec) {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const horizontal = Math.abs(dx) > Math.abs(dy);
  if (horizontal) {
    const pad = 16;
    const dir = Math.sign(dx);
    return { x1: a.x + dir * pad, y1: a.y, x2: b.x - dir * pad, y2: b.y, horizontal };
  }
  const dir = Math.sign(dy);
  return {
    x1: a.x,
    y1: a.y + dir * 38,
    x2: b.x,
    y2: b.y - dir * 38,
    horizontal,
  };
}

/**
 * A schematic route map of the request path — the section's visual anchor,
 * not a decorative flourish. Every edge here is a real call in the codebase
 * (see EDGES above); the detail cards below the diagram fill in what each
 * stop actually does.
 */
export function ArchitectureDiagram({ landmarks }: { landmarks: Landmark[] }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const byId = new Map(landmarks.map((l) => [l.id, l]));

  return (
    <div className="w-full overflow-x-auto rounded-sm border border-graphite/20 bg-deep-chart/30 p-4 sm:p-6">
      <svg
        viewBox="0 0 860 400"
        className="h-auto w-full min-w-[640px]"
        role="img"
        aria-label="Architecture diagram: browser request flows through the gateway to the agent loop, which searches the vault and calls the generation backend; a separate ingestion worker writes into the vault."
      >
        {EDGES.map((e, i) => {
          const a = node(e.from);
          const b = node(e.to);
          const active = hovered === e.from || hovered === e.to;
          const stroke = e.kind === "primary" ? BRASS : e.kind === "secondary" ? VERDIGRIS : GRAPHITE;
          const { x1, y1, x2, y2, horizontal } = connector(a, b);
          const labelX = horizontal ? (x1 + x2) / 2 : x2 + 12;
          const labelY = horizontal ? Math.min(y1, y2) - 10 : (y1 + y2) / 2 + 3;
          return (
            <g key={i} opacity={hovered && !active ? 0.25 : 1} style={{ transition: "opacity 200ms" }}>
              <line
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke={stroke}
                strokeWidth={active ? 2.5 : 1.5}
                strokeDasharray={e.kind === "dashed" ? "5 5" : undefined}
                markerEnd={`url(#arrow-${e.kind})`}
                style={{ transition: "stroke-width 200ms" }}
              />
              {e.label && (
                <text
                  x={labelX}
                  y={labelY}
                  textAnchor={horizontal ? "middle" : "start"}
                  className="font-mono uppercase"
                  fontSize={10}
                  letterSpacing={0.5}
                  fill={GRAPHITE}
                >
                  {e.label}
                </text>
              )}
            </g>
          );
        })}

        <defs>
          {(["primary", "secondary", "dashed"] as const).map((kind) => (
            <marker
              key={kind}
              id={`arrow-${kind}`}
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path
                d="M0,0 L10,5 L0,10 z"
                fill={kind === "primary" ? BRASS : kind === "secondary" ? VERDIGRIS : GRAPHITE}
              />
            </marker>
          ))}
        </defs>

        {NODES.map((n) => {
          const l = byId.get(n.id);
          if (!l) return null;
          const active = hovered === n.id;
          return (
            <g
              key={n.id}
              onMouseEnter={() => setHovered(n.id)}
              onMouseLeave={() => setHovered(null)}
              style={{ cursor: "default" }}
            >
              <circle
                cx={n.x}
                cy={n.y}
                r={active ? 9 : 7}
                fill={active ? BRASS : "#16232F"}
                stroke={active ? BRASS : GRAPHITE}
                strokeWidth={1.5}
                style={{ transition: "all 200ms" }}
              />
              <text
                x={n.x}
                y={n.y - 20}
                textAnchor="middle"
                fontSize={13}
                fill={active ? PARCHMENT : "#D9D3C0"}
                className="font-display"
                style={{ transition: "fill 200ms" }}
              >
                {l.name}
              </text>
              <text
                x={n.x}
                y={n.y + 26}
                textAnchor="middle"
                fontSize={9.5}
                letterSpacing={0.5}
                fill={active ? VERDIGRIS : GRAPHITE}
                className="font-mono uppercase"
                style={{ transition: "fill 200ms" }}
              >
                {l.subtitle}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-2 font-mono text-[0.65rem] uppercase tracking-cartouche text-graphite">
        Hover a stop for its name · brass = hot request path · teal = cache/ingest · dashed = generation call
      </p>
    </div>
  );
}
