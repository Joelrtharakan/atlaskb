"use client";

import { useFrame, useThree } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import type { AtlasNode } from "./layout";

// The functional Living Atlas, reimagined as a literal atlas: a slowly rotating
// wireframe globe (graticule) with the tenant's documents as glowing points on
// its surface, great-circle arcs between related documents, and — on a question
// — a beacon route lighting up across the sphere. Contained and centered by a
// fixed camera; the globe holds still while an answer is framed.

const INK = "#16232B";
const GRAPHITE = "#515C63";
const MERIDIAN = "#22B2A6";
const BEACON = "#E8A22B";

const R = 3.2; // globe radius

/** Deterministic unit points spread over a sphere (Fibonacci lattice). */
function spherePoint(i: number, n: number): THREE.Vector3 {
  const y = n <= 1 ? 0 : 1 - (i / (n - 1)) * 2;
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = Math.PI * (3 - Math.sqrt(5)) * i;
  return new THREE.Vector3(Math.cos(theta) * r, y, Math.sin(theta) * r);
}

/** Line segments for a globe graticule (parallels + meridians). */
function graticuleGeometry(): THREE.BufferGeometry {
  const pts: number[] = [];
  const seg = 96;
  const push = (a: THREE.Vector3, b: THREE.Vector3) => pts.push(a.x, a.y, a.z, b.x, b.y, b.z);

  // Parallels (latitude circles).
  for (const latDeg of [-60, -40, -20, 0, 20, 40, 60]) {
    const lat = (latDeg * Math.PI) / 180;
    const y = Math.sin(lat) * R;
    const ring = Math.cos(lat) * R;
    for (let i = 0; i < seg; i++) {
      const a = (i / seg) * Math.PI * 2;
      const b = ((i + 1) / seg) * Math.PI * 2;
      push(
        new THREE.Vector3(Math.cos(a) * ring, y, Math.sin(a) * ring),
        new THREE.Vector3(Math.cos(b) * ring, y, Math.sin(b) * ring),
      );
    }
  }
  // Meridians (longitude great circles through the poles).
  const meridians = 12;
  for (let m = 0; m < meridians; m++) {
    const lon = (m / meridians) * Math.PI * 2;
    for (let i = 0; i < seg; i++) {
      const t0 = (i / seg) * Math.PI * 2;
      const t1 = ((i + 1) / seg) * Math.PI * 2;
      const at = (t: number) =>
        new THREE.Vector3(Math.sin(t) * Math.cos(lon) * R, Math.cos(t) * R, Math.sin(t) * Math.sin(lon) * R);
      push(at(t0), at(t1));
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
  return geo;
}

/** A great-circle arc (slerp) between two surface points, as segment endpoints. */
function arcPoints(a: THREE.Vector3, b: THREE.Vector3, steps = 24): THREE.Vector3[] {
  const ua = a.clone().normalize();
  const ub = b.clone().normalize();
  let dot = THREE.MathUtils.clamp(ua.dot(ub), -1, 1);
  const omega = Math.acos(dot);
  const out: THREE.Vector3[] = [];
  if (omega < 1e-4) return [a.clone(), b.clone()];
  const sin = Math.sin(omega);
  // Lift the arc slightly above the surface so it reads as an arc, not a chord.
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const s1 = Math.sin((1 - t) * omega) / sin;
    const s2 = Math.sin(t * omega) / sin;
    const p = ua.clone().multiplyScalar(s1).add(ub.clone().multiplyScalar(s2));
    const lift = 1 + Math.sin(t * Math.PI) * 0.06;
    out.push(p.multiplyScalar(R * lift));
  }
  return out;
}

function segmentsFromPolyline(points: THREE.Vector3[]): number[] {
  const pts: number[] = [];
  for (let i = 0; i < points.length - 1; i++) {
    pts.push(points[i].x, points[i].y, points[i].z, points[i + 1].x, points[i + 1].y, points[i + 1].z);
  }
  return pts;
}

interface Props {
  nodes: AtlasNode[];
  activeIds: string[];
  citedIds: string[];
  highlightedId: string | null;
  focus: boolean;
  reducedMotion: boolean;
}

export function AtlasGlobe({ nodes, activeIds, citedIds, highlightedId, focus, reducedMotion }: Props) {
  const group = useRef<THREE.Group>(null);
  const cores = useRef<THREE.InstancedMesh>(null);
  const halos = useRef<THREE.InstancedMesh>(null);
  const { camera } = useThree();
  const dummy = useMemo(() => new THREE.Object3D(), []);

  // Place each document on the globe; index order is stable per corpus.
  const positions = useMemo(
    () => nodes.map((_, i) => spherePoint(i, nodes.length).multiplyScalar(R)),
    [nodes],
  );
  const posById = useMemo(() => {
    const m = new Map<string, THREE.Vector3>();
    nodes.forEach((n, i) => m.set(n.id, positions[i]));
    return m;
  }, [nodes, positions]);

  const graticule = useMemo(() => graticuleGeometry(), []);

  // Latent arcs between each node and its two nearest neighbours (angular).
  const latentArcs = useMemo(() => {
    const pts: number[] = [];
    const seen = new Set<string>();
    positions.forEach((p, i) => {
      const dists = positions
        .map((q, j) => ({ j, d: i === j ? Infinity : p.angleTo(q) }))
        .sort((a, b) => a.d - b.d)
        .slice(0, 2);
      for (const { j } of dists) {
        const key = i < j ? `${i}-${j}` : `${j}-${i}`;
        if (seen.has(key)) continue;
        seen.add(key);
        pts.push(...segmentsFromPolyline(arcPoints(positions[i], positions[j], 16)));
      }
    });
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(pts), 3));
    return geo;
  }, [positions]);

  // Beacon route: great-circle arcs chaining the retrieved documents.
  const routeGeom = useRef<THREE.BufferGeometry>(null);
  const routeMat = useRef<THREE.LineBasicMaterial>(null);
  const activePositions = useMemo(
    () => activeIds.map((id) => posById.get(id)).filter((v): v is THREE.Vector3 => !!v),
    [activeIds, posById],
  );
  const routeArray = useMemo(() => {
    if (activePositions.length < 2) return new Float32Array(0);
    const pts: number[] = [];
    for (let i = 0; i < activePositions.length - 1; i++) {
      pts.push(...segmentsFromPolyline(arcPoints(activePositions[i], activePositions[i + 1], 28)));
    }
    return new Float32Array(pts);
  }, [activePositions]);

  useLayoutEffect(() => {
    positions.forEach((p, i) => {
      dummy.position.copy(p);
      dummy.scale.setScalar(0.08);
      dummy.updateMatrix();
      cores.current?.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(0.16);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(i, dummy.matrix);
    });
    if (cores.current) cores.current.instanceMatrix.needsUpdate = true;
    if (halos.current) halos.current.instanceMatrix.needsUpdate = true;
    // Fixed pleasant tilt.
    if (group.current) group.current.rotation.x = 0.32;
  }, [positions, dummy]);

  useLayoutEffect(() => {
    if (routeGeom.current) {
      routeGeom.current.setAttribute("position", new THREE.BufferAttribute(routeArray, 3));
      routeGeom.current.attributes.position.needsUpdate = true;
    }
  }, [routeArray]);

  const activeSet = useMemo(() => new Set(activeIds), [activeIds]);
  const citedSet = useMemo(() => new Set(citedIds), [citedIds]);

  useFrame((state, delta) => {
    // Fixed framing on the origin — never zoom out of the frame. A whisper of
    // dolly on focus, but bounded so the globe always fits.
    const targetZ = focus ? 9.3 : 9.6;
    camera.position.x += (0 - camera.position.x) * Math.min(1, delta * 2);
    camera.position.y += (0.15 - camera.position.y) * Math.min(1, delta * 2);
    camera.position.z += (targetZ - camera.position.z) * Math.min(1, delta * 2);
    camera.lookAt(0, 0, 0);

    // Rotate the globe; hold nearly still while an answer is framed.
    if (group.current && !reducedMotion) {
      group.current.rotation.y += delta * (focus ? 0.02 : 0.09);
    }

    // Route fades in when active.
    if (routeMat.current) {
      const target = focus && activePositions.length >= 2 ? 0.85 : 0;
      routeMat.current.opacity += (target - routeMat.current.opacity) * Math.min(1, delta * 4);
    }

    // Retrieved → gold accent; else ink core with a teal glow. A subtle pulse,
    // and crisp (small) sizes so lit nodes read as accents, not blobs.
    const pulse = reducedMotion ? 1 : 1 + 0.08 * Math.sin(state.clock.elapsedTime * 3);
    const color = new THREE.Color();
    const halo = new THREE.Color();
    nodes.forEach((n, i) => {
      const active = activeSet.has(n.id);
      const cited = citedSet.has(n.id);
      const hi = highlightedId === n.id;
      const lit = active || hi;
      color.set(lit ? BEACON : INK);
      halo.set(lit ? BEACON : MERIDIAN);
      cores.current?.setColorAt(i, color);
      halos.current?.setColorAt(i, halo);
      const coreScale = (hi ? 0.12 : cited ? 0.1 : active ? 0.1 : 0.08) * (lit ? pulse : 1);
      const haloScale = (lit ? 0.22 : 0.16) * (lit ? pulse : 1);
      dummy.position.copy(positions[i]);
      dummy.scale.setScalar(coreScale);
      dummy.updateMatrix();
      cores.current?.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(haloScale);
      dummy.updateMatrix();
      halos.current?.setMatrixAt(i, dummy.matrix);
    });
    if (cores.current) {
      cores.current.instanceMatrix.needsUpdate = true;
      if (cores.current.instanceColor) cores.current.instanceColor.needsUpdate = true;
    }
    if (halos.current) {
      halos.current.instanceMatrix.needsUpdate = true;
      if (halos.current.instanceColor) halos.current.instanceColor.needsUpdate = true;
    }
  });

  if (nodes.length === 0) return null;

  return (
    <group ref={group}>
      <lineSegments geometry={graticule}>
        <lineBasicMaterial color={GRAPHITE} transparent opacity={0.13} depthWrite={false} />
      </lineSegments>
      <lineSegments geometry={latentArcs}>
        <lineBasicMaterial color={MERIDIAN} transparent opacity={0.3} depthWrite={false} />
      </lineSegments>
      <lineSegments>
        <bufferGeometry ref={routeGeom} />
        <lineBasicMaterial ref={routeMat} color={BEACON} transparent opacity={0} depthWrite={false} />
      </lineSegments>
      {/* Base colour is white so per-instance colours (ink / teal / gold) render
          true — a tinted base would multiply and muddy them. */}
      <instancedMesh ref={halos} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 10, 10]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.38} depthWrite={false} />
      </instancedMesh>
      <instancedMesh ref={cores} args={[undefined, undefined, nodes.length]}>
        <sphereGeometry args={[1, 14, 14]} />
        <meshBasicMaterial color="#ffffff" />
      </instancedMesh>
    </group>
  );
}
