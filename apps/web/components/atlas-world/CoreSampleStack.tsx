"use client";

// A vertical stack of extracted strata. Simple box-per-layer composition; the
// "considered" part is that thickness and color are real chunk data, and hover
// reads back the exact stratum — turning "rows in a table" into something legible
// at a glance. Hover-offset easing timing referenced from Aceternity/Magic UI
// card micro-interactions, rebuilt in the token system (no stock component used).

import { useFrame } from "@react-three/fiber";
import { useRef, useState } from "react";
import * as THREE from "three";

import { ATLAS } from "./tokens";

export interface CoreLayer {
  id: string;
  /** Relative thickness (e.g. chunk length); normalized internally. */
  thickness: number;
  /** Color for this stratum — map confidence/staleness onto this upstream. */
  color: string;
}

export interface CoreSampleStackProps {
  layers: CoreLayer[];
  hoveredId?: string | null;
  onHover?: (id: string | null) => void;
  /** Total world height of the stack. */
  height?: number;
  radius?: number;
  reducedMotion?: boolean;
}

function Layer({
  color,
  y,
  thickness,
  radius,
  hovered,
  reducedMotion,
  onOver,
  onOut,
}: {
  color: string;
  y: number;
  thickness: number;
  radius: number;
  hovered: boolean;
  reducedMotion: boolean;
  onOver: () => void;
  onOut: () => void;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_, delta) => {
    if (!ref.current) return;
    // Hovered stratum eases outward (along +X) so it reads as "pulled for inspection".
    const targetX = hovered ? radius * 0.5 : 0;
    if (reducedMotion) {
      ref.current.position.x = targetX;
    } else {
      ref.current.position.x += (targetX - ref.current.position.x) * Math.min(1, delta * 8);
    }
  });
  return (
    <mesh
      ref={ref}
      position={[0, y, 0]}
      onPointerOver={(e) => {
        e.stopPropagation();
        onOver();
      }}
      onPointerOut={onOut}
    >
      <cylinderGeometry args={[radius, radius, Math.max(0.02, thickness), 48]} />
      <meshStandardMaterial
        color={color}
        emissive={color}
        emissiveIntensity={hovered ? 0.45 : 0.12}
        roughness={0.7}
        metalness={0.15}
      />
    </mesh>
  );
}

function Stack({
  layers,
  hoveredId,
  onHover,
  height = 5,
  radius = 0.9,
  reducedMotion = false,
}: CoreSampleStackProps) {
  const group = useRef<THREE.Group>(null);
  const [internalHover, setInternalHover] = useState<string | null>(null);
  const hovered = hoveredId !== undefined ? hoveredId : internalHover;

  const total = layers.reduce((s, l) => s + Math.max(0.0001, l.thickness), 0) || 1;
  const gap = 0.012;

  // Slow idle rotation so the core reads as a 3D object; frozen on reduced motion.
  useFrame((_, delta) => {
    if (reducedMotion || !group.current) return;
    group.current.rotation.y += delta * 0.25;
  });

  let cursor = -height / 2;
  const setHover = (id: string | null) => {
    if (hoveredId === undefined) setInternalHover(id);
    onHover?.(id);
  };

  return (
    <group ref={group}>
      {layers.map((l) => {
        const h = (Math.max(0.0001, l.thickness) / total) * height - gap;
        const y = cursor + h / 2;
        cursor += h + gap;
        return (
          <Layer
            key={l.id}
            color={l.color}
            y={y}
            thickness={h}
            radius={radius}
            hovered={hovered === l.id}
            reducedMotion={reducedMotion}
            onOver={() => setHover(l.id)}
            onOut={() => setHover(null)}
          />
        );
      })}
    </group>
  );
}

/**
 * A geological core sample of a document's chunks. Layer thickness ~ chunk
 * length; color encodes retrieval-confidence / staleness. Hovering a stratum
 * fires onHover(id) so the page can show that chunk's text in a side panel.
 * Render inside an AtlasCanvas; the side panel stays usable if the scene fails.
 */
export function CoreSampleStack(props: CoreSampleStackProps) {
  return (
    <>
      <ambientLight intensity={0.7} />
      <directionalLight position={[3, 4, 5]} intensity={1.0} color={ATLAS.parchment} />
      <Stack {...props} />
    </>
  );
}
