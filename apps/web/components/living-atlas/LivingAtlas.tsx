"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { AtlasGlobe } from "./AtlasGlobe";
import { generativeAtlas, type AtlasEdge, type AtlasNode } from "./layout";

// Design tokens (kept in sync with tailwind.config.ts / the Phase 1 plan).
const MERIDIAN = "#22B2A6"; // verdigris accent — ambient threads + node glow

const CENTER = new THREE.Vector3(0, 0, 0);

export type { AtlasNode, AtlasEdge } from "./layout";

export interface LivingAtlasProps {
  mode?: "ambient" | "functional";
  /** Functional: the tenant's document nodes. Ambient: generated if omitted. */
  nodes?: AtlasNode[];
  edges?: AtlasEdge[];
  /** Document ids the current retrieval hit (drive camera + answer threads). */
  activeIds?: string[];
  /** Document ids actually cited by the answer (extra glow). */
  citedIds?: string[];
  /** A citation being hovered in the panel → highlight its node. */
  highlightedId?: string | null;
  /** When true, frame the active cluster; when false, ease back to ambient. */
  focus?: boolean;
  reducedMotion?: boolean;
  /** World-space X offset for the whole field (ambient landing shifts it right). */
  offsetX?: number;
}

/** Instanced document nodes: solid cores + two soft halo layers (a bloom-like
 * glow). Optionally drift organically (each node bobs on its own phase) and
 * twinkle. */
function Nodes({
  nodes,
  coreColor,
  haloColor,
  haloOpacity,
  twinkle = false,
  drift = false,
  reducedMotion = false,
}: {
  nodes: AtlasNode[];
  coreColor: string;
  haloColor: string;
  haloOpacity: number;
  twinkle?: boolean;
  drift?: boolean;
  reducedMotion?: boolean;
}) {
  const cores = useRef<THREE.InstancedMesh>(null);
  const halos = useRef<THREE.InstancedMesh>(null);
  const glow = useRef<THREE.InstancedMesh>(null);
  const haloMat = useRef<THREE.MeshBasicMaterial>(null);
  const glowMat = useRef<THREE.MeshBasicMaterial>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // Per-node motion parameters, seeded deterministically from the index.
  const motion = useMemo(
    () =>
      nodes.map((_, i) => {
        const seed = i * 127.1 + 0.5;
        return {
          phase: (Math.sin(seed) * 43758.5453) % (Math.PI * 2),
          speed: 0.35 + Math.abs(Math.cos(seed * 1.7)) * 0.4,
          ampY: 0.06 + Math.abs(Math.sin(seed)) * 0.06,
          ampX: 0.04 + Math.abs(Math.cos(seed)) * 0.04,
        };
      }),
    [nodes],
  );

  const writeMatrices = (time: number) => {
    nodes.forEach((node, i) => {
      const m = motion[i];
      const active = drift && !reducedMotion;
      const dx = active ? Math.cos(time * m.speed * 0.7 + m.phase) * m.ampX : 0;
      const dy = active ? Math.sin(time * m.speed + m.phase) * m.ampY : 0;
      dummy.position.set(node.position[0] + dx, node.position[1] + dy, node.position[2]);
      dummy.scale.setScalar(node.scale);
      dummy.updateMatrix();
      cores.current?.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(node.scale * 1.9);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(node.scale * 3.2);
      dummy.updateMatrix();
      glow.current?.setMatrixAt(i, dummy.matrix);
    });
    for (const mesh of [cores, halos, glow]) {
      if (mesh.current) mesh.current.instanceMatrix.needsUpdate = true;
    }
  };

  useLayoutEffect(() => {
    writeMatrices(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (drift && !reducedMotion) writeMatrices(t);
    if (twinkle && !reducedMotion && haloMat.current && glowMat.current) {
      haloMat.current.opacity = haloOpacity * (0.85 + 0.15 * Math.sin(t * 0.9));
      glowMat.current.opacity = haloOpacity * 0.22 * (0.7 + 0.3 * Math.sin(t * 0.9 + 1.5));
    }
  });

  if (nodes.length === 0) return null;

  return (
    <group>
      <instancedMesh ref={glow} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 8, 8]} />
        <meshBasicMaterial
          ref={glowMat}
          color={haloColor}
          transparent
          opacity={haloOpacity * 0.22}
          depthWrite={false}
        />
      </instancedMesh>
      <instancedMesh ref={halos} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 12, 12]} />
        <meshBasicMaterial
          ref={haloMat}
          color={haloColor}
          transparent
          opacity={haloOpacity}
          depthWrite={false}
        />
      </instancedMesh>
      <instancedMesh ref={cores} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 14, 14]} />
        <meshBasicMaterial color={coreColor} />
      </instancedMesh>
    </group>
  );
}

/** Latent structure between nodes — quiet threads. */
function LatentThreads({
  nodes,
  edges,
  color,
  opacity,
}: {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  color: string;
  opacity: number;
}) {
  const geometry = useMemo(() => {
    const positions = new Float32Array(edges.length * 6);
    edges.forEach((edge, i) => {
      positions.set(nodes[edge.a].position, i * 6);
      positions.set(nodes[edge.b].position, i * 6 + 3);
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geo;
  }, [nodes, edges]);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} />
    </lineSegments>
  );
}

/**
 * The signature ambient motion: luminous "signal" pulses that travel along the
 * threads from node to node, fading in as they leave and out as they arrive —
 * the knowledge map quietly routing between related places. Each pulse re-homes
 * to a fresh random edge when it lands, so routes keep lighting up across the
 * field. (Ambient only; rendered nowhere when reduced motion is set.)
 */
function SignalPulses({
  nodes,
  edges,
  count = 10,
}: {
  nodes: AtlasNode[];
  edges: AtlasEdge[];
  count: number;
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
      speed: 0.18 + Math.random() * 0.28,
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
        pulse.speed = 0.18 + Math.random() * 0.28;
      }
      const e = edges[pulse.edge];
      a.set(...nodes[e.a].position);
      b.set(...nodes[e.b].position);
      const eased = pulse.t * pulse.t * (3 - 2 * pulse.t); // smoothstep
      p.copy(a).lerp(b, eased);
      // Emit → travel → absorb: grow toward the middle of the run, shrink at ends.
      const envelope = Math.sin(pulse.t * Math.PI);
      dummy.position.copy(p);
      dummy.scale.setScalar(0.04 + envelope * 0.14);
      dummy.updateMatrix();
      mesh.current.setMatrixAt(i, dummy.matrix);
    }
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, count]}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshBasicMaterial color={MERIDIAN} transparent opacity={0.95} depthWrite={false} />
    </instancedMesh>
  );
}

/** Ambient rotation for the landing page. Frozen when reduced motion is set.
 * Keeps the camera locked on the origin so the (recentred) field stays centered. */
function AmbientRotation({
  groupRef,
  reducedMotion,
}: {
  groupRef: React.RefObject<THREE.Group>;
  reducedMotion: boolean;
}) {
  const { camera } = useThree();
  useFrame((state, delta) => {
    camera.lookAt(CENTER);
    if (reducedMotion || !groupRef.current) return;
    // Very slow drift — the traveling signal pulses carry the motion now.
    groupRef.current.rotation.y += delta * 0.02; // ~1 rev / 5 min
    const t = state.clock.elapsedTime;
    // Gentle wobble only — no translation, so the cloud never drifts off-centre.
    groupRef.current.rotation.x = 0.1 + Math.sin(t * 0.08) * 0.04;
  });
  return null;
}

function Scene({
  mode,
  data,
  activeIds,
  citedIds,
  highlightedId,
  focus,
  reducedMotion,
  offsetX,
}: Required<Omit<LivingAtlasProps, "nodes" | "edges">> & {
  data: { nodes: AtlasNode[]; edges: AtlasEdge[] };
}) {
  const group = useRef<THREE.Group>(null);

  // A composed static pose so the frozen (reduced-motion) frame reads well.
  // Small tilt only. Ambient shifts the whole field to the right (offsetX) so
  // the cartouche on the left sits over clean paper.
  useLayoutEffect(() => {
    if (mode === "ambient" && group.current) {
      group.current.rotation.set(0.12, 0.3, 0);
      group.current.position.x = offsetX;
    }
  }, [mode, offsetX]);

  const isFunctional = mode === "functional";

  // Functional (chat): a slowly rotating wireframe globe of the tenant's
  // documents, with a beacon route lighting up on retrieval.
  if (isFunctional) {
    return (
      <AtlasGlobe
        nodes={data.nodes}
        activeIds={activeIds}
        citedIds={citedIds}
        highlightedId={highlightedId}
        focus={focus}
        reducedMotion={reducedMotion}
      />
    );
  }

  // Ambient (landing): a drifting verdigris constellation with signal pulses.
  return (
    <>
      <AmbientRotation groupRef={group} reducedMotion={reducedMotion} />
      <group ref={group}>
        <LatentThreads nodes={data.nodes} edges={data.edges} color={MERIDIAN} opacity={0.2} />
        <Nodes
          nodes={data.nodes}
          coreColor={MERIDIAN}
          haloColor={MERIDIAN}
          haloOpacity={0.32}
          twinkle
          drift
          reducedMotion={reducedMotion}
        />
        {!reducedMotion && data.edges.length > 0 && (
          <SignalPulses nodes={data.nodes} edges={data.edges} count={10} />
        )}
      </group>
    </>
  );
}

/**
 * The Living Atlas signature element. Ambient mode drifts as a verdigris
 * constellation; functional mode lights beacon nodes and draws amber answer
 * threads as real retrieval happens.
 */
export default function LivingAtlas({
  mode = "ambient",
  nodes,
  edges,
  activeIds = [],
  citedIds = [],
  highlightedId = null,
  focus = false,
  reducedMotion = false,
  offsetX = 0,
}: LivingAtlasProps) {
  const data = useMemo(() => {
    if (nodes && edges) return { nodes, edges };
    if (nodes) return { nodes, edges: [] };
    return generativeAtlas();
  }, [nodes, edges]);

  return (
    <Canvas
      className="h-full w-full"
      camera={{ position: [0, 0, 14], fov: 45 }}
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
      dpr={[1, 1.75]}
    >
      <Scene
        mode={mode}
        data={data}
        activeIds={activeIds}
        citedIds={citedIds}
        highlightedId={highlightedId}
        focus={focus}
        reducedMotion={reducedMotion}
        offsetX={offsetX}
      />
    </Canvas>
  );
}
