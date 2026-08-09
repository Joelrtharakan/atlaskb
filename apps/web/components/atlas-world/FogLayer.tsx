"use client";

// Shader-based fog: each patch is a gaussian falloff summed in the fragment
// shader into an alpha mask. Uniform-array + per-patch falloff approach referenced
// from Three.js Journey's shader lessons; rebuilt so patches are real content-gap
// clusters and "clearing" is a data event (intensity eased to 0), not decoration.

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { ATLAS } from "./tokens";

const MAX_PATCHES = 16;

export interface FogPatch {
  id: string;
  /** Center in normalized plane space (0..1, 0..1). */
  x: number;
  y: number;
  /** Radius in normalized units. */
  radius: number;
  /** 0..1 — how thick the fog is; ease to 0 to "resolve"/clear a gap. */
  intensity: number;
}

export interface FogLayerProps {
  patches: FogPatch[];
  size?: number;
  /** Lift above the terrain it overlays. */
  y?: number;
  color?: string;
  reducedMotion?: boolean;
}

const VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

const FRAG = /* glsl */ `
  precision highp float;
  varying vec2 vUv;
  uniform int uCount;
  uniform vec4 uPatch[${MAX_PATCHES}]; // xy=center, z=radius, w=intensity
  uniform vec3 uColor;
  uniform float uTime;

  // cheap value noise so the fog edge shimmers instead of being a clean circle
  float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p){
    vec2 i = floor(p), f = fract(p);
    float a = hash(i), b = hash(i+vec2(1.,0.)), c = hash(i+vec2(0.,1.)), d = hash(i+vec2(1.,1.));
    vec2 u = f*f*(3.-2.*f);
    return mix(mix(a,b,u.x), mix(c,d,u.x), u.y);
  }

  void main() {
    float fog = 0.0;
    for (int i = 0; i < ${MAX_PATCHES}; i++) {
      if (i >= uCount) break;
      vec4 p = uPatch[i];
      float d = distance(vUv, p.xy);
      float g = exp(-(d*d) / (2.0 * p.z * p.z));
      fog += g * p.w;
    }
    float n = noise(vUv * 8.0 + uTime * 0.05) * 0.25;
    float a = clamp(fog * (0.85 + n), 0.0, 0.92);
    gl_FragColor = vec4(uColor, a);
  }
`;

function Fog({ patches, size = 6, y = 0.05, color = ATLAS.parchment, reducedMotion = false }: FogLayerProps) {
  // Current (animated) intensities, eased toward the target patch intensities.
  const current = useRef<Map<string, number>>(new Map());

  const uniforms = useMemo(
    () => ({
      uCount: { value: 0 },
      uPatch: { value: Array.from({ length: MAX_PATCHES }, () => new THREE.Vector4()) },
      uColor: { value: new THREE.Color(color) },
      uTime: { value: 0 },
    }),
    [color],
  );

  const writeUniforms = () => {
    const list = patches.slice(0, MAX_PATCHES);
    uniforms.uCount.value = list.length;
    list.forEach((p, i) => {
      const cur = current.current.get(p.id) ?? p.intensity;
      (uniforms.uPatch.value[i] as THREE.Vector4).set(p.x, p.y, Math.max(0.0001, p.radius), cur);
    });
  };

  useFrame((state, delta) => {
    // Ease each patch's live intensity toward its target (fog forming / clearing).
    patches.forEach((p) => {
      const cur = current.current.get(p.id) ?? (reducedMotion ? p.intensity : 0);
      const next = reducedMotion ? p.intensity : cur + (p.intensity - cur) * Math.min(1, delta / 1.5);
      current.current.set(p.id, next);
    });
    if (!reducedMotion) uniforms.uTime.value = state.clock.elapsedTime;
    writeUniforms();
  });

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, y, 0]}>
      <planeGeometry args={[size, size, 1, 1]} />
      <shaderMaterial
        vertexShader={VERT}
        fragmentShader={FRAG}
        uniforms={uniforms}
        transparent
        depthWrite={false}
      />
    </mesh>
  );
}

/**
 * Data-driven fog. Used by Admin Content Gaps (Fog of War): each unresolved
 * content-gap cluster is a patch obscuring the relief map; resolving a gap eases
 * that patch to zero and the fog visibly clears (~1.5s). Render inside an
 * AtlasCanvas, typically layered above a TerrainField.
 */
export function FogLayer(props: FogLayerProps) {
  return <Fog {...props} />;
}
