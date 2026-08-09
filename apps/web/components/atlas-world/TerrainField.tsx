"use client";

// Height-map / vertex-displacement approach adapted from Three.js Journey's
// terrain chapter (BufferGeometry + per-vertex color ramp), rebuilt to be driven
// by real data (a normalized height grid) rather than procedural noise.

import { OrbitControls } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { ATLAS } from "./tokens";

export interface TerrainMarker {
  /** Position in normalized grid space (0..1, 0..1). */
  x: number;
  z: number;
  color?: string;
  label?: string;
}

export interface TerrainFieldProps {
  /**
   * Normalized height grid (values 0..1), rows of columns. This is the "real
   * data" input — e.g. document access-frequency/size per cell, valleys for
   * stale docs. Bilinearly sampled onto the display mesh.
   */
  heights: number[][];
  /** Display mesh resolution (segments per side). */
  segments?: number;
  /** World size of the plane. */
  size?: number;
  /** Peak height in world units. */
  relief?: number;
  colorLow?: string;
  colorHigh?: string;
  /** Ease terrain up from flat on mount (~2s) — the "terrain forming" moment. */
  autoForm?: boolean;
  /** Controlled form amount 0..1 (overrides autoForm when provided). */
  form?: number;
  markers?: TerrainMarker[];
  orbit?: boolean;
  reducedMotion?: boolean;
  /** Draw topographic contour isolines across the relief (the survey look). */
  contours?: boolean;
}

/** Bilinear sample of a normalized grid at (u,v) in [0,1]. */
function sampleGrid(grid: number[][], u: number, v: number): number {
  const rows = grid.length;
  const cols = grid[0]?.length ?? 0;
  if (rows === 0 || cols === 0) return 0;
  const gx = u * (cols - 1);
  const gy = v * (rows - 1);
  const x0 = Math.floor(gx);
  const y0 = Math.floor(gy);
  const x1 = Math.min(x0 + 1, cols - 1);
  const y1 = Math.min(y0 + 1, rows - 1);
  const tx = gx - x0;
  const ty = gy - y0;
  const a = grid[y0][x0] * (1 - tx) + grid[y0][x1] * tx;
  const b = grid[y1][x0] * (1 - tx) + grid[y1][x1] * tx;
  return a * (1 - ty) + b * ty;
}

function Relief({
  heights,
  segments = 96,
  size = 6,
  relief = 1.4,
  colorLow = ATLAS.verdigris,
  colorHigh = ATLAS.brass,
  autoForm = false,
  form,
  markers = [],
  reducedMotion = false,
  contours = false,
}: TerrainFieldProps) {
  const meshRef = useRef<THREE.Mesh>(null);
  const formRef = useRef(autoForm && !reducedMotion ? 0 : 1);

  // Base geometry + the undisplaced height each vertex *wants*, precomputed once.
  // Also the four-stop elevation palette: a deep valley floor, verdigris slopes,
  // brass highlands, and a bright parchment cap — reads as a real relief map.
  const { geometry, baseHeights, ramp } = useMemo(() => {
    const geo = new THREE.PlaneGeometry(size, size, segments, segments);
    geo.rotateX(-Math.PI / 2); // lie flat: displace along +Y
    const pos = geo.attributes.position;
    const count = pos.count;
    const bh = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const u = (x + size / 2) / size;
      const v = (z + size / 2) / size;
      bh[i] = sampleGrid(heights, u, v);
    }
    geo.setAttribute("color", new THREE.BufferAttribute(new Float32Array(count * 3), 3));

    const low = new THREE.Color(colorLow);
    const high = new THREE.Color(colorHigh);
    const floor = low.clone().multiplyScalar(0.5); // deep valley
    const cap = high.clone().lerp(new THREE.Color(ATLAS.parchment), 0.55); // sunlit peak
    const out = new THREE.Color();
    const ramp = (h: number, target: THREE.Color) => {
      if (h < 0.4) target.copy(floor).lerp(low, h / 0.4);
      else if (h < 0.72) target.copy(low).lerp(high, (h - 0.4) / 0.32);
      else target.copy(high).lerp(cap, (h - 0.72) / 0.28);
      return target;
    };
    // warm the very peaks slightly for depth
    void out;
    return { geometry: geo, baseHeights: bh, ramp };
  }, [heights, segments, size, colorLow, colorHigh]);

  // Smooth, banded material with optional topographic contour isolines injected
  // into the standard material's shader (keeps real lighting; adds cartography).
  const material = useMemo(() => {
    const m = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.82,
      metalness: 0.08,
    });
    if (!contours) return m;
    m.onBeforeCompile = (shader) => {
      shader.uniforms.uInterval = { value: Math.max(0.0001, relief / 7) };
      shader.uniforms.uContour = { value: 0.5 };
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying float vElev;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvElev = position.y;");
      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          "#include <common>\nvarying float vElev;\nuniform float uInterval;\nuniform float uContour;",
        )
        .replace(
          "#include <dithering_fragment>",
          `float _e = vElev / uInterval;
           float _f = abs(fract(_e - 0.5) - 0.5);
           float _line = 1.0 - smoothstep(0.0, fwidth(_e) * 1.5, _f);
           gl_FragColor.rgb = mix(gl_FragColor.rgb, gl_FragColor.rgb * 0.45, _line * uContour);
           #include <dithering_fragment>`,
        );
    };
    return m;
  }, [contours, relief]);

  // Apply displacement + color ramp for the current form amount.
  const applyForm = (amount: number) => {
    const geo = meshRef.current?.geometry as THREE.BufferGeometry | undefined;
    if (!geo) return;
    const pos = geo.attributes.position as THREE.BufferAttribute;
    const col = geo.attributes.color as THREE.BufferAttribute;
    const c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      const h = baseHeights[i];
      pos.setY(i, h * relief * amount);
      ramp(h, c);
      col.setXYZ(i, c.r, c.g, c.b);
    }
    pos.needsUpdate = true;
    col.needsUpdate = true;
    geo.computeVertexNormals();
  };

  useLayoutEffect(() => {
    applyForm(form ?? formRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, form]);

  useFrame((_, delta) => {
    if (form !== undefined) return; // controlled by parent
    if (formRef.current >= 1) return;
    formRef.current = Math.min(1, formRef.current + delta / 2); // ~2s ease-in
    applyForm(formRef.current);
  });

  const activeForm = form ?? formRef.current;

  return (
    <group>
      <mesh ref={meshRef} geometry={geometry} material={material} />
      {markers.map((m, i) => {
        const h = sampleGrid(heights, m.x, m.z) * relief * activeForm;
        const wx = (m.x - 0.5) * size;
        const wz = (m.z - 0.5) * size;
        return (
          <mesh key={i} position={[wx, h + 0.28, wz]}>
            <coneGeometry args={[0.09, 0.34, 6]} />
            <meshStandardMaterial
              color={m.color ?? ATLAS.signalAmber}
              emissive={m.color ?? ATLAS.signalAmber}
              emissiveIntensity={0.5}
            />
          </mesh>
        );
      })}
    </group>
  );
}

/**
 * A reusable topographic relief map. Height is real data (document
 * frequency/size, staleness valleys, query volume) — never random noise. Used
 * by the Dashboard (Relief Map), Onboarding (Terrain Forming), and as the base
 * layer under the Content-Gaps Fog of War.
 *
 * Render this inside an AtlasCanvas so degradation/lazy-load is handled once.
 */
export function TerrainField(props: TerrainFieldProps) {
  const { orbit = false, reducedMotion = false } = props;
  return (
    <>
      <ambientLight intensity={0.55} />
      {/* warm key from the west, cool fill from the east → readable relief */}
      <directionalLight position={[5, 7, 3]} intensity={1.25} color={ATLAS.parchment} />
      <directionalLight position={[-4, 3, -2]} intensity={0.4} color={ATLAS.verdigris} />
      <Relief {...props} />
      {orbit && (
        <OrbitControls
          enablePan={false}
          enableZoom
          autoRotate={!reducedMotion}
          autoRotateSpeed={0.4}
          minPolarAngle={0.2}
          maxPolarAngle={Math.PI / 2.2}
        />
      )}
    </>
  );
}
