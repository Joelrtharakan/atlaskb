"use client";

// Reuses the connection-thread / travelling-pulse technique already built for
// the Living Atlas (Phase 5 SignalPulses + LatentThreads) rather than rebuilding
// it. Generalized into two data-driven modes:
//   - "flow":  pulse density/speed encode a real rate (e.g. query volume) → Trade Winds
//   - "sweep": a single radar arc rotates once, lighting matched nodes as it passes → Search

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { ATLAS } from "./tokens";

export interface ThreadNode {
  id: string;
  position: [number, number, number];
}
export interface ThreadEdge {
  a: number;
  b: number;
}

export interface ThreadFieldProps {
  nodes: ThreadNode[];
  edges?: ThreadEdge[];
  mode?: "flow" | "sweep";
  /** flow: number of travelling pulses (map real query volume onto this). */
  pulseCount?: number;
  /** flow: base pulse speed multiplier (map real rate onto this). */
  pulseSpeed?: number;
  /** sweep: ids of nodes that are actual results — they latch lit as swept. */
  matchedIds?: string[];
  reducedMotion?: boolean;
}

function LatentThreads({ nodes, edges }: { nodes: ThreadNode[]; edges: ThreadEdge[] }) {
  const geometry = useMemo(() => {
    const positions = new Float32Array(edges.length * 6);
    edges.forEach((e, i) => {
      positions.set(nodes[e.a].position, i * 6);
      positions.set(nodes[e.b].position, i * 6 + 3);
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geo;
  }, [nodes, edges]);
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={ATLAS.threadCyan} transparent opacity={0.18} depthWrite={false} />
    </lineSegments>
  );
}

/** Travelling pulses along edges — emit→travel→absorb, re-homing on arrival. */
function FlowPulses({
  nodes,
  edges,
  count,
  speed,
}: {
  nodes: ThreadNode[];
  edges: ThreadEdge[];
  count: number;
  speed: number;
}) {
  const mesh = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const a = useMemo(() => new THREE.Vector3(), []);
  const b = useMemo(() => new THREE.Vector3(), []);
  const p = useMemo(() => new THREE.Vector3(), []);
  const pulses = useRef(
    Array.from({ length: count }, () => ({
      edge: Math.floor(Math.random() * Math.max(1, edges.length)),
      t: Math.random(),
      speed: (0.18 + Math.random() * 0.28) * speed,
    })),
  );

  useFrame((_, delta) => {
    if (!mesh.current || edges.length === 0) return;
    for (let i = 0; i < count; i++) {
      const pulse = pulses.current[i];
      pulse.t += pulse.speed * delta;
      if (pulse.t >= 1 || pulse.edge >= edges.length) {
        pulse.edge = Math.floor(Math.random() * edges.length);
        pulse.t = 0;
        pulse.speed = (0.18 + Math.random() * 0.28) * speed;
      }
      const e = edges[pulse.edge];
      a.set(...nodes[e.a].position);
      b.set(...nodes[e.b].position);
      const eased = pulse.t * pulse.t * (3 - 2 * pulse.t);
      p.copy(a).lerp(b, eased);
      const envelope = Math.sin(pulse.t * Math.PI);
      dummy.position.copy(p);
      dummy.scale.setScalar(0.03 + envelope * 0.12);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 10, 10]} />
      <meshBasicMaterial color={ATLAS.threadCyan} transparent opacity={0.95} depthWrite={false} />
    </instancedMesh>
  );
}

/**
 * Radar sweep: a thin arc rotates once around the field; a matched node latches
 * lit (amber) the moment the arc crosses its bearing. Deliberately quick and
 * un-narrative — "search is raw and fast".
 */
function Sweep({
  nodes,
  matchedIds,
  reducedMotion,
}: {
  nodes: ThreadNode[];
  matchedIds: Set<string>;
  reducedMotion: boolean;
}) {
  const arc = useRef<THREE.Group>(null);
  const cores = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const color = useMemo(() => new THREE.Color(), []);
  const amber = useMemo(() => new THREE.Color(ATLAS.signalAmber), []);
  const dim = useMemo(() => new THREE.Color(ATLAS.verdigris), []);

  const bearings = useMemo(
    () => nodes.map((n) => Math.atan2(n.position[1], n.position[0])),
    [nodes],
  );
  const angle = useRef(reducedMotion ? Math.PI * 2 : -Math.PI); // start swept if frozen
  const lit = useRef<number[]>(nodes.map(() => (reducedMotion ? 1 : 0)));

  const write = () => {
    if (!cores.current) return;
    nodes.forEach((n, i) => {
      const isMatch = matchedIds.has(n.id);
      const l = lit.current[i];
      dummy.position.set(...n.position);
      dummy.scale.setScalar(0.12 + (isMatch ? l * 0.22 : 0));
      dummy.updateMatrix();
      cores.current!.setMatrixAt(i, dummy.matrix);
      color.copy(dim).lerp(amber, isMatch ? l : 0);
      cores.current!.setColorAt(i, color);
    });
    cores.current.instanceMatrix.needsUpdate = true;
    if (cores.current.instanceColor) cores.current.instanceColor.needsUpdate = true;
  };

  useFrame((_, delta) => {
    if (reducedMotion) return;
    if (angle.current < Math.PI) {
      const prev = angle.current;
      angle.current = Math.min(Math.PI, angle.current + delta * 5.2); // ~1.2s full sweep
      // Latch any node whose bearing the arc just crossed.
      nodes.forEach((_, i) => {
        if (bearings[i] > prev && bearings[i] <= angle.current) lit.current[i] = 1;
      });
      if (arc.current) arc.current.rotation.z = angle.current;
    }
    // Ease latched nodes up.
    lit.current = lit.current.map((l, i) =>
      matchedIds.has(nodes[i].id) && l > 0 ? Math.min(1, l + delta * 3) : l,
    );
    write();
  });

  return (
    <group>
      <group ref={arc}>
        <mesh>
          <planeGeometry args={[6, 0.02]} />
          <meshBasicMaterial color={ATLAS.signalAmber} transparent opacity={0.7} />
        </mesh>
      </group>
      <instancedMesh ref={cores} args={[undefined, undefined, Math.max(1, nodes.length)]}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
    </group>
  );
}

/**
 * The shared thread/particle system. Compose it wherever a page draws
 * relationships or flow between nodes — do not hand-roll a second particle
 * system. Render inside an AtlasCanvas.
 */
export function ThreadField({
  nodes,
  edges = [],
  mode = "flow",
  pulseCount = 12,
  pulseSpeed = 1,
  matchedIds = [],
  reducedMotion = false,
}: ThreadFieldProps) {
  const matched = useMemo(() => new Set(matchedIds), [matchedIds]);
  if (nodes.length === 0) return null;
  return (
    <group>
      {edges.length > 0 && <LatentThreads nodes={nodes} edges={edges} />}
      {mode === "flow" && !reducedMotion && edges.length > 0 && (
        <FlowPulses nodes={nodes} edges={edges} count={pulseCount} speed={pulseSpeed} />
      )}
      {mode === "sweep" && <Sweep nodes={nodes} matchedIds={matched} reducedMotion={reducedMotion} />}
    </group>
  );
}
