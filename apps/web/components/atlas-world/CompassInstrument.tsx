"use client";

// Ring + needle instrument. Easing/drift timing referenced from Three.js Journey
// animation lessons (damped approach + low-amplitude idle), rebuilt in the
// brass/verdigris token system rather than any stock component.

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { ATLAS } from "./tokens";

export interface CompassInstrumentProps {
  /** Target heading in radians the needle eases toward. */
  heading?: number;
  /** Gentle idle wobble when there's no meaningful heading ("finding your way in"). */
  drift?: boolean;
  size?: number;
  reducedMotion?: boolean;
}

function Compass({ heading, drift = true, size = 1.6, reducedMotion = false }: CompassInstrumentProps) {
  const needle = useRef<THREE.Group>(null);
  const ring = useRef<THREE.Group>(null);
  const brass = useMemo(() => new THREE.Color(ATLAS.brass), []);
  const verdigris = useMemo(() => new THREE.Color(ATLAS.verdigris), []);

  // Tick marks around the rose (N/E/S/W emphasized), built once.
  const ticks = useMemo(() => {
    const out: { angle: number; major: boolean }[] = [];
    for (let i = 0; i < 32; i++) {
      out.push({ angle: (i / 32) * Math.PI * 2, major: i % 8 === 0 });
    }
    return out;
  }, []);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    if (!needle.current) return;
    if (reducedMotion) {
      needle.current.rotation.z = heading ?? 0.4; // composed static pose
      return;
    }
    // Damped approach toward heading, plus a faint drift so it never sits dead still.
    const target = (heading ?? 0) + (drift ? Math.sin(t * 0.35) * 0.28 : 0);
    needle.current.rotation.z += (target - needle.current.rotation.z) * Math.min(1, delta * 2.5);
    if (ring.current) ring.current.rotation.z = Math.sin(t * 0.12) * 0.05;
  });

  return (
    <group>
      <group ref={ring}>
        {/* Outer bezel */}
        <mesh>
          <torusGeometry args={[size, size * 0.045, 16, 64]} />
          <meshStandardMaterial color={brass} metalness={0.7} roughness={0.35} />
        </mesh>
        {/* Rose face */}
        <mesh position={[0, 0, -0.02]}>
          <circleGeometry args={[size * 0.96, 64]} />
          <meshStandardMaterial color={ATLAS.ink} metalness={0.1} roughness={0.9} />
        </mesh>
        {ticks.map((tk, i) => {
          const r = size * (tk.major ? 0.78 : 0.86);
          const len = tk.major ? size * 0.16 : size * 0.07;
          return (
            <mesh
              key={i}
              position={[Math.cos(tk.angle) * r, Math.sin(tk.angle) * r, 0]}
              rotation={[0, 0, tk.angle + Math.PI / 2]}
            >
              <planeGeometry args={[tk.major ? 0.02 : 0.01, len]} />
              <meshBasicMaterial color={tk.major ? brass : verdigris} />
            </mesh>
          );
        })}
      </group>

      {/* Needle: brass north arm, verdigris south arm, pivoting on center. */}
      <group ref={needle}>
        <mesh position={[0, size * 0.34, 0.02]}>
          <coneGeometry args={[size * 0.08, size * 0.68, 4]} />
          <meshStandardMaterial color={ATLAS.signalAmber} metalness={0.5} roughness={0.4} />
        </mesh>
        <mesh position={[0, -size * 0.28, 0.02]} rotation={[0, 0, Math.PI]}>
          <coneGeometry args={[size * 0.07, size * 0.56, 4]} />
          <meshStandardMaterial color={verdigris} metalness={0.4} roughness={0.5} />
        </mesh>
        <mesh position={[0, 0, 0.03]}>
          <cylinderGeometry args={[size * 0.06, size * 0.06, 0.05, 16]} />
          <meshStandardMaterial color={brass} metalness={0.8} roughness={0.3} />
        </mesh>
      </group>
    </group>
  );
}

/**
 * A modest brass compass. On auth pages it drifts gently with no functional
 * meaning ("finding your way in"); elsewhere a `heading` can point it at
 * something real. Render inside an AtlasCanvas.
 */
export function CompassInstrument(props: CompassInstrumentProps) {
  return (
    <>
      <ambientLight intensity={0.8} />
      <directionalLight position={[2, 3, 4]} intensity={0.9} color={ATLAS.parchment} />
      <Compass {...props} />
    </>
  );
}
