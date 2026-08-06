"use client";

import { useLayoutEffect, useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

import { buildAtlas, type AtlasNode, type AtlasEdge } from "./atlas-data";
import { useReducedMotion } from "./use-reduced-motion";

// Design tokens (kept in sync with tailwind.config.ts).
const INK = "#16232B";
const GRAPHITE = "#515C63";
const BEACON = "#E8A22B"; // RESERVED: retrieval active (lit nodes)
const MERIDIAN = "#22B2A6"; // RESERVED: active connection threads

export interface AtlasState {
  /** Node indices currently lit by an active retrieval. */
  activeNodes: number[];
  /** Ordered node indices forming the lit route (meridian threads). */
  route: number[];
  /** Whether the camera should frame the active cluster. */
  focus: boolean;
}

const IDLE_STATE: AtlasState = { activeNodes: [], route: [], focus: false };

/** Document nodes as instanced ink survey marks (latent, always present). */
function BaseNodes({ nodes }: { nodes: AtlasNode[] }) {
  const ref = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = ref.current;
    if (!mesh) return;
    const dummy = new THREE.Object3D();
    nodes.forEach((node, i) => {
      dummy.position.set(...node.position);
      dummy.scale.setScalar(node.scale);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);
    });
    mesh.instanceMatrix.needsUpdate = true;
  }, [nodes]);

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, nodes.length]}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshBasicMaterial color={INK} />
    </instancedMesh>
  );
}

/** Latent structure — quiet graphite, never meridian. */
function LatentThreads({ nodes, edges }: { nodes: AtlasNode[]; edges: AtlasEdge[] }) {
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
      <lineBasicMaterial color={GRAPHITE} transparent opacity={0.22} />
    </lineSegments>
  );
}

/** Nodes lit by an active retrieval — beacon amber, gently pulsing in place. */
function ActiveNodes({
  nodes,
  activeNodes,
  reducedMotion,
}: {
  nodes: AtlasNode[];
  activeNodes: number[];
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);

  useFrame((state) => {
    if (reducedMotion || !group.current) return;
    // Scale each node about its own centre so it breathes without drifting.
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 3) * 0.12;
    group.current.children.forEach((child) => child.scale.setScalar(pulse));
  });

  return (
    <group ref={group}>
      {activeNodes.map((i) => (
        <mesh key={i} position={nodes[i].position}>
          <sphereGeometry args={[nodes[i].scale * 1.7, 16, 16]} />
          <meshBasicMaterial color={BEACON} />
        </mesh>
      ))}
    </group>
  );
}

/** The lit route between co-retrieved nodes — meridian, fading in. */
function RouteThreads({ nodes, route }: { nodes: AtlasNode[]; route: number[] }) {
  const materialRef = useRef<THREE.LineBasicMaterial>(null);

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    if (route.length < 2) return geo;
    // Expand the path into consecutive segments: (r0,r1),(r1,r2),…
    const positions = new Float32Array((route.length - 1) * 6);
    for (let i = 0; i < route.length - 1; i++) {
      positions.set(nodes[route[i]].position, i * 6);
      positions.set(nodes[route[i + 1]].position, i * 6 + 3);
    }
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return geo;
  }, [nodes, route]);

  // Ease the route in rather than popping.
  useFrame((_, delta) => {
    const mat = materialRef.current;
    if (!mat) return;
    const target = route.length >= 2 ? 0.85 : 0;
    mat.opacity += (target - mat.opacity) * Math.min(1, delta * 5);
  });

  if (route.length < 2) return null;

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial ref={materialRef} color={MERIDIAN} transparent opacity={0} />
    </lineSegments>
  );
}

/**
 * Camera behaviour for reactive mode: a slow idle orbit that yields to framing
 * the active cluster when a retrieval is in progress, then settles back.
 */
function CameraRig({
  nodes,
  state,
  reducedMotion,
}: {
  nodes: AtlasNode[];
  state: AtlasState;
  reducedMotion: boolean;
}) {
  const { camera } = useThree();
  const angle = useRef(0);
  const lookAt = useRef(new THREE.Vector3(0, 0, 0));
  const desired = useRef(new THREE.Vector3(0, 0, 14));

  const centroid = useMemo(() => {
    const c = new THREE.Vector3();
    if (state.activeNodes.length === 0) return c;
    state.activeNodes.forEach((i) => c.add(new THREE.Vector3(...nodes[i].position)));
    return c.multiplyScalar(1 / state.activeNodes.length);
  }, [nodes, state.activeNodes]);

  useFrame((_, delta) => {
    // Reduced motion: cut, don't ease — snap to target, no idle orbit.
    const posK = reducedMotion ? 1 : Math.min(1, delta * 1.8);
    const lookK = reducedMotion ? 1 : Math.min(1, delta * 2.5);
    if (!reducedMotion) angle.current += delta * 0.05; // idle orbit underneath

    if (state.focus && state.activeNodes.length > 0) {
      desired.current.copy(centroid).add(new THREE.Vector3(0, 1.5, 7));
      lookAt.current.lerp(centroid, lookK);
    } else {
      const r = 14;
      const a = reducedMotion ? 0 : angle.current;
      desired.current.set(Math.sin(a) * r, 2, Math.cos(a) * r);
      lookAt.current.lerp(new THREE.Vector3(0, 0, 0), lookK);
    }

    camera.position.lerp(desired.current, posK);
    camera.lookAt(lookAt.current);
  });

  return null;
}

/** Ambient rotation for the landing page (no retrieval, neutrals only). */
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
  data,
  mode,
  state,
  reducedMotion,
}: {
  data: { nodes: AtlasNode[]; edges: AtlasEdge[] };
  mode: "ambient" | "reactive";
  state: AtlasState;
  reducedMotion: boolean;
}) {
  const group = useRef<THREE.Group>(null);

  return (
    <>
      {mode === "ambient" && <AmbientRotation groupRef={group} reducedMotion={reducedMotion} />}
      {mode === "reactive" && (
        <CameraRig nodes={data.nodes} state={state} reducedMotion={reducedMotion} />
      )}
      <group ref={group}>
        <LatentThreads nodes={data.nodes} edges={data.edges} />
        <BaseNodes nodes={data.nodes} />
        {mode === "reactive" && (
          <>
            <RouteThreads nodes={data.nodes} route={state.route} />
            <ActiveNodes
              nodes={data.nodes}
              activeNodes={state.activeNodes}
              reducedMotion={reducedMotion}
            />
          </>
        )}
      </group>
    </>
  );
}

export interface LivingAtlasProps {
  /** "ambient" = landing (rotating, neutrals only). "reactive" = chat. */
  mode?: "ambient" | "reactive";
  /** Precomputed constellation. Defaults to a dense ambient field. */
  data?: { nodes: AtlasNode[]; edges: AtlasEdge[] };
  /** Reactive retrieval state (reactive mode only). */
  state?: AtlasState;
}

/**
 * The Living Atlas signature element. Ambient by default; in reactive mode it
 * lights beacon nodes / meridian routes and frames them as retrieval happens.
 */
export default function LivingAtlas({ mode = "ambient", data, state }: LivingAtlasProps) {
  const reducedMotion = useReducedMotion();
  const resolved = useMemo(() => data ?? buildAtlas(), [data]);

  return (
    <Canvas
      className="h-full w-full"
      camera={{ position: [0, 0, 14], fov: 45 }}
      gl={{ alpha: true, antialias: true }}
      dpr={[1, 2]}
    >
      <Scene
        data={resolved}
        mode={mode}
        state={state ?? IDLE_STATE}
        reducedMotion={reducedMotion}
      />
    </Canvas>
  );
}
