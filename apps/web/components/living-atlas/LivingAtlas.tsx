"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { generativeAtlas, type AtlasEdge, type AtlasNode } from "./layout";

// Design tokens (kept in sync with tailwind.config.ts / the Phase 1 plan).
const INK = "#16232B";
const GRAPHITE = "#515C63";
const BEACON = "#E8A22B"; // RESERVED: retrieval active / citations
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
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Instanced document nodes: solid cores + a soft coloured halo (the "glow"). */
function Nodes({
  nodes,
  coreColor,
  haloColor,
  haloOpacity,
}: {
  nodes: AtlasNode[];
  coreColor: string;
  haloColor: string;
  haloOpacity: number;
}) {
  const cores = useRef<THREE.InstancedMesh>(null);
  const halos = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const dummy = new THREE.Object3D();
    nodes.forEach((node, i) => {
      dummy.position.set(...node.position);
      dummy.scale.setScalar(node.scale);
      dummy.updateMatrix();
      cores.current?.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(node.scale * 2.6);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(i, dummy.matrix);
    });
    if (cores.current) cores.current.instanceMatrix.needsUpdate = true;
    if (halos.current) halos.current.instanceMatrix.needsUpdate = true;
  }, [nodes]);

  if (nodes.length === 0) return null;

  return (
    <group>
      <instancedMesh ref={halos} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 10, 10]} />
        <meshBasicMaterial
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

/** Beacon overlays for retrieved / cited / hovered nodes. */
function Highlights({
  positions,
  citedPositions,
  highlightedPosition,
  reducedMotion,
}: {
  positions: THREE.Vector3[];
  citedPositions: Set<number>;
  highlightedPosition: THREE.Vector3 | null;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (!group.current) return;
    const pulse = reducedMotion ? 1 : 1 + Math.sin(state.clock.elapsedTime * 3) * 0.12;
    group.current.children.forEach((child) => child.scale.setScalar(pulse));
  });

  return (
    <group ref={group}>
      {positions.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[citedPositions.has(i) ? 0.34 : 0.24, 16, 16]} />
          <meshBasicMaterial color={BEACON} transparent opacity={citedPositions.has(i) ? 0.95 : 0.7} />
        </mesh>
      ))}
      {highlightedPosition ? (
        <mesh position={highlightedPosition}>
          <sphereGeometry args={[0.5, 18, 18]} />
          <meshBasicMaterial color={BEACON} transparent opacity={0.35} depthWrite={false} />
        </mesh>
      ) : null}
    </group>
  );
}

/** Amber threads drawn progressively from each active node to the answer point. */
function AnswerThreads({
  positions,
  focus,
  reducedMotion,
}: {
  positions: THREE.Vector3[];
  focus: boolean;
  reducedMotion: boolean;
}) {
  const geo = useRef<THREE.BufferGeometry>(null);
  const mat = useRef<THREE.LineBasicMaterial>(null);
  const progress = useRef<number[]>([]);
  const array = useRef<Float32Array>(new Float32Array(0));
  const end = useMemo(() => new THREE.Vector3(), []);

  useFrame((_, delta) => {
    const n = positions.length;
    if (progress.current.length !== n) {
      progress.current = new Array(n).fill(reducedMotion ? 1 : 0);
      array.current = new Float32Array(n * 6);
    }
    if (n === 0) {
      if (mat.current) mat.current.opacity = 0;
      return;
    }
    const target = focus ? 1 : 0;
    let maxP = 0;
    for (let i = 0; i < n; i++) {
      let p = progress.current[i];
      // Ease toward the target; slightly staggered so threads draw in sequence.
      const rate = focus ? 3.0 + i * 0.15 : 4.5;
      p = reducedMotion ? target : p + (target - p) * Math.min(1, delta * rate);
      progress.current[i] = p;
      maxP = Math.max(maxP, p);
      const start = positions[i];
      end.copy(start).lerp(CENTER, easeOutCubic(p));
      array.current.set(
        [start.x, start.y, start.z, end.x, end.y, end.z],
        i * 6,
      );
    }
    if (geo.current) {
      geo.current.setAttribute("position", new THREE.BufferAttribute(array.current, 3));
      geo.current.attributes.position.needsUpdate = true;
      geo.current.setDrawRange(0, n * 2);
    }
    if (mat.current) mat.current.opacity = 0.9 * maxP;
  });

  if (positions.length === 0) return null;

  return (
    <lineSegments>
      <bufferGeometry ref={geo} />
      <lineBasicMaterial ref={mat} color={BEACON} transparent opacity={0} depthWrite={false} linewidth={2} />
    </lineSegments>
  );
}

/** The central "answer" point — lights while an active retrieval is framed. */
function AnswerPoint({ visible, reducedMotion }: { visible: boolean; reducedMotion: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((state, delta) => {
    if (!ref.current || !mat.current) return;
    const targetOpacity = visible ? 0.95 : 0;
    mat.current.opacity += (targetOpacity - mat.current.opacity) * Math.min(1, delta * 4);
    const pulse = reducedMotion ? 1 : 1 + Math.sin(state.clock.elapsedTime * 2.5) * 0.15;
    ref.current.scale.setScalar(pulse);
  });
  return (
    <mesh ref={ref} position={[0, 0, 0]}>
      <sphereGeometry args={[0.28, 18, 18]} />
      <meshBasicMaterial ref={mat} color={BEACON} transparent opacity={0} />
    </mesh>
  );
}

/** Slow idle orbit that eases to frame the active cluster, then settles back. */
function CameraRig({
  activePositions,
  focus,
  reducedMotion,
}: {
  activePositions: THREE.Vector3[];
  focus: boolean;
  reducedMotion: boolean;
}) {
  const { camera } = useThree();
  const angle = useRef(0);
  const lookAt = useRef(new THREE.Vector3(0, 0, 0));
  const desired = useRef(new THREE.Vector3(0, 0, 14));

  const centroid = useMemo(() => {
    const c = new THREE.Vector3();
    if (activePositions.length === 0) return c;
    activePositions.forEach((p) => c.add(p));
    return c.multiplyScalar(1 / activePositions.length);
  }, [activePositions]);

  useFrame((_, delta) => {
    const posK = reducedMotion ? 1 : Math.min(1, delta * 1.6);
    const lookK = reducedMotion ? 1 : Math.min(1, delta * 2.2);
    if (!reducedMotion) angle.current += delta * 0.05; // gentle idle orbit

    if (focus && activePositions.length > 0) {
      // Pull the camera toward the lit cluster, offset so threads to the centre
      // stay in frame.
      desired.current.copy(centroid).multiplyScalar(0.55).add(new THREE.Vector3(0, 1.2, 9));
      lookAt.current.lerp(centroid.clone().multiplyScalar(0.5), lookK);
    } else {
      const r = 14;
      const a = reducedMotion ? 0.6 : angle.current;
      desired.current.set(Math.sin(a) * r, 2, Math.cos(a) * r);
      lookAt.current.lerp(CENTER, lookK);
    }
    camera.position.lerp(desired.current, posK);
    camera.lookAt(lookAt.current);
  });

  return null;
}

/** Ambient rotation for the landing page. Frozen when reduced motion is set. */
function AmbientRotation({
  groupRef,
  reducedMotion,
}: {
  groupRef: React.RefObject<THREE.Group>;
  reducedMotion: boolean;
}) {
  useFrame((state, delta) => {
    if (reducedMotion || !groupRef.current) return;
    groupRef.current.rotation.y += delta * 0.03; // ~1 rev / 3.5 min
    const t = state.clock.elapsedTime;
    groupRef.current.rotation.x = Math.sin(t * 0.08) * 0.06;
    groupRef.current.position.y = Math.sin(t * 0.12) * 0.15;
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
}: Required<Omit<LivingAtlasProps, "nodes" | "edges">> & {
  data: { nodes: AtlasNode[]; edges: AtlasEdge[] };
}) {
  const group = useRef<THREE.Group>(null);

  // A composed static pose so the frozen (reduced-motion) frame reads well.
  useLayoutEffect(() => {
    if (mode === "ambient" && group.current) {
      group.current.rotation.set(0.15, 0.6, 0);
    }
  }, [mode]);

  const indexById = useMemo(() => {
    const m = new Map<string, number>();
    data.nodes.forEach((n, i) => m.set(n.id, i));
    return m;
  }, [data.nodes]);

  const toVec = (id: string): THREE.Vector3 | null => {
    const i = indexById.get(id);
    return i == null ? null : new THREE.Vector3(...data.nodes[i].position);
  };

  const activePositions = useMemo(
    () => activeIds.map(toVec).filter((v): v is THREE.Vector3 => v !== null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeIds, data.nodes],
  );
  const citedSet = useMemo(() => {
    const s = new Set<number>();
    activeIds.forEach((id, i) => {
      if (citedIds.includes(id)) s.add(i);
    });
    return s;
  }, [activeIds, citedIds]);
  const highlightedPosition = highlightedId ? toVec(highlightedId) : null;

  const isFunctional = mode === "functional";

  return (
    <>
      {isFunctional ? (
        <CameraRig
          activePositions={activePositions}
          focus={focus}
          reducedMotion={reducedMotion}
        />
      ) : (
        <AmbientRotation groupRef={group} reducedMotion={reducedMotion} />
      )}

      <group ref={group}>
        <LatentThreads
          nodes={data.nodes}
          edges={data.edges}
          color={isFunctional ? GRAPHITE : MERIDIAN}
          opacity={isFunctional ? 0.18 : 0.24}
        />
        <Nodes
          nodes={data.nodes}
          coreColor={isFunctional ? INK : MERIDIAN}
          haloColor={MERIDIAN}
          haloOpacity={isFunctional ? 0.16 : 0.3}
        />
      </group>

      {isFunctional && (
        <>
          <AnswerThreads
            positions={activePositions}
            focus={focus}
            reducedMotion={reducedMotion}
          />
          <AnswerPoint
            visible={focus && activePositions.length > 0}
            reducedMotion={reducedMotion}
          />
          <Highlights
            positions={activePositions}
            citedPositions={citedSet}
            highlightedPosition={highlightedPosition}
            reducedMotion={reducedMotion}
          />
        </>
      )}
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
      />
    </Canvas>
  );
}
