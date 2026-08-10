"use client";

import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

import { useCapabilities } from "@/components/living-atlas/use-capabilities";

import { PULSE_DURATION, SURVEY_END, randomPulseInterval, sampleTimeline } from "./heroTimeline";

const S = 11;
const R = 2.3;
const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

interface Peak {
  u: number;
  v: number;
  amp: number;
  w: number;
  active: boolean;
  /** Invented but plausible metres, kept consistent with `amp` (taller bump →
   *  higher reading) so the numbers don't contradict the terrain shape. */
  elevation?: number;
}
const PEAKS: Peak[] = [
  { u: 0.4, v: 0.52, amp: 0.8, w: 0.12, active: true, elevation: 2140 },
  { u: 0.58, v: 0.36, amp: 0.66, w: 0.1, active: true, elevation: 1860 },
  { u: 0.7, v: 0.6, amp: 0.58, w: 0.095, active: true, elevation: 1690 },
  { u: 0.26, v: 0.32, amp: 0.42, w: 0.13, active: false },
  { u: 0.5, v: 0.72, amp: 0.34, w: 0.12, active: false },
  { u: 0.86, v: 0.28, amp: 0.3, w: 0.1, active: false },
];
// The query point: on the terrain's near-left shoulder. Deliberately kept well
// inside the frame (was 0.13/0.86, which fell under the copy scrim and off the
// bottom edge, so the route appeared to trail in from nowhere).
const ORIGIN_UV = { u: 0.26, v: 0.7 };
const targets = PEAKS.filter((p) => p.active);

// --- Ambient scene runtime ---------------------------------------------------
// Drives the two-tier cadence: a fast intro on mount, then a periodic
// travelling-glow "pulse" that re-verifies the already-drawn route without a
// hard reset, and (rarely) a full redraw when the hero returns to view after
// being scrolled away for a while. Plain mutable object (not React state) —
// it's read and written from inside useFrame, so nothing here should trigger
// a re-render.
interface SceneRuntime {
  /** clock.elapsedTime at which the current intro/redraw started. */
  introStart: number;
  pulseStart: number | null;
  nextPulseAt: number | null;
  flareStart: number | null;
  nextFlareAt: number | null;
  resetRequested: boolean;
  tabHidden: boolean;
}
function createRuntime(): SceneRuntime {
  return {
    introStart: 0,
    pulseStart: null,
    nextPulseAt: null,
    flareStart: null,
    nextFlareAt: null,
    resetRequested: false,
    tabHidden: typeof document !== "undefined" && document.visibilityState === "hidden",
  };
}
/** How long the hero must have been scrolled out of view before a return
 *  triggers a full redraw-from-scratch instead of just resuming. */
const AWAY_RESET_MS = 60_000;

const FLARE_MIN_INTERVAL = 60;
const FLARE_MAX_INTERVAL = 120;
const FLARE_DURATION = 0.7;
const randomFlareInterval = () =>
  FLARE_MIN_INTERVAL + Math.random() * (FLARE_MAX_INTERVAL - FLARE_MIN_INTERVAL);

function sampleFromRuntime(now: number, runtime: SceneRuntime, reduced: boolean) {
  const effectiveElapsed = now - runtime.introStart;
  const pulseElapsed =
    !runtime.tabHidden && runtime.pulseStart !== null ? now - runtime.pulseStart : -1;
  return sampleTimeline(effectiveElapsed, reduced, pulseElapsed);
}

/** Advances the runtime's intro/pulse/flare scheduling. Registered first in
 *  the tree so it runs before anything that reads `runtime` this frame. */
function TimelineDriver({ runtime, reduced }: { runtime: SceneRuntime; reduced: boolean }) {
  useFrame((state) => {
    const now = state.clock.elapsedTime;
    if (runtime.resetRequested) {
      runtime.introStart = now;
      runtime.pulseStart = null;
      runtime.nextPulseAt = null;
      runtime.flareStart = null;
      runtime.nextFlareAt = null;
      runtime.resetRequested = false;
    }
    if (reduced || runtime.tabHidden) return;
    const effectiveElapsed = now - runtime.introStart;
    if (effectiveElapsed < SURVEY_END) return;

    if (runtime.nextPulseAt === null) {
      runtime.nextPulseAt = now + randomPulseInterval();
    } else if (runtime.pulseStart === null && now >= runtime.nextPulseAt) {
      runtime.pulseStart = now;
    } else if (runtime.pulseStart !== null && now - runtime.pulseStart > PULSE_DURATION) {
      runtime.pulseStart = null;
      runtime.nextPulseAt = now + randomPulseInterval();
    }

    if (runtime.nextFlareAt === null) {
      runtime.nextFlareAt = now + randomFlareInterval();
    } else if (runtime.flareStart === null && now >= runtime.nextFlareAt) {
      runtime.flareStart = now;
    } else if (runtime.flareStart !== null && now - runtime.flareStart > FLARE_DURATION) {
      runtime.flareStart = null;
      runtime.nextFlareAt = now + randomFlareInterval();
    }
  });
  return null;
}

// --- Layered value-noise terrain (in-house; no noise lib) ------------------
function hash2(x: number, y: number): number {
  const s = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return s - Math.floor(s);
}
function vnoise(x: number, y: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  return (
    hash2(xi, yi) * (1 - u) * (1 - v) +
    hash2(xi + 1, yi) * u * (1 - v) +
    hash2(xi, yi + 1) * (1 - u) * v +
    hash2(xi + 1, yi + 1) * u * v
  );
}
function fbm(x: number, y: number): number {
  // Four octaves — large-scale shape with small-scale roughness on top.
  let a = 0;
  let amp = 0.55;
  let f = 1;
  for (let o = 0; o < 4; o++) {
    a += amp * vnoise(x * f + o * 7.3, y * f + o * 3.1);
    f *= 2.03;
    amp *= 0.5;
  }
  return a;
}
function heightAt(u: number, v: number): number {
  let h = 0.08 + 0.34 * fbm(u * 3.0, v * 3.0);
  for (const p of PEAKS) {
    const du = u - p.u;
    const dv = v - p.v;
    h += p.amp * Math.exp(-(du * du + dv * dv) / (2 * p.w * p.w));
  }
  return Math.min(1, h);
}
function world(u: number, v: number, lift = 0): [number, number, number] {
  return [(u - 0.5) * S, heightAt(u, v) * R + lift, (v - 0.5) * S];
}

interface LanternState {
  active: boolean;
  point: THREE.Vector3;
}

function Terrain({
  reduced,
  lantern,
}: {
  reduced: boolean;
  lantern: { current: LanternState };
}) {
  const { geometry, material } = useMemo(() => {
    const seg = 82;
    const geo = new THREE.PlaneGeometry(S, S, seg, seg);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const u = (pos.getX(i) + S / 2) / S;
      const v = (pos.getZ(i) + S / 2) / S;
      pos.setY(i, heightAt(u, v) * R);
    }
    geo.computeVertexNormals(); // smooth normals

    // Second pass: colour by elevation AND slope (flat→moss, steep→rock, active
    // peak caps→warm brass).
    const nrm = geo.attributes.normal;
    const colors = new Float32Array(pos.count * 3);
    const lowland = new THREE.Color("#15222E");
    const moss = new THREE.Color("#3C5A52");
    const rock = new THREE.Color("#474640");
    const brass = new THREE.Color("#7A5326");
    const base = new THREE.Color();
    const c = new THREE.Color();
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i);
      const z = pos.getZ(i);
      const h = pos.getY(i) / R;
      const flat = Math.max(0, nrm.getY(i)); // 1 flat, →0 steep
      base.copy(lowland).lerp(moss, THREE.MathUtils.smoothstep(h, 0.12, 0.6));
      c.copy(rock).lerp(base, Math.pow(flat, 1.5)); // steep faces show rock
      // warm brass on the caps of the active target peaks
      let warm = 0;
      for (const p of targets) {
        const dx = x - (p.u - 0.5) * S;
        const dz = z - (p.v - 0.5) * S;
        warm = Math.max(warm, Math.exp(-(dx * dx + dz * dz) / (2 * (p.w * S * 0.8) ** 2)));
      }
      c.lerp(brass, warm * Math.max(0, (h - 0.55) / 0.45) * 0.7);
      // Depth cue: darken the flat, unlit skirts of the mesh so the eye stays on
      // the ridge instead of wandering to the edges. (Cheaper than a DoF pass
      // and it survives the fog, which only reads on the far edge.)
      const edge = Math.max(Math.abs(x), Math.abs(z)) / (S / 2);
      c.multiplyScalar(1 - THREE.MathUtils.smoothstep(edge, 0.55, 1.0) * 0.72);
      colors.set([c.r, c.g, c.b], i * 3);
    }
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));

    const mat = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.78,
      metalness: 0.08,
    });
    mat.onBeforeCompile = (shader) => {
      shader.uniforms.uInterval = { value: R / 9 };
      shader.vertexShader = shader.vertexShader
        .replace("#include <common>", "#include <common>\nvarying float vElev;")
        .replace("#include <begin_vertex>", "#include <begin_vertex>\nvElev = position.y;");
      shader.fragmentShader = shader.fragmentShader
        .replace(
          "#include <common>",
          "#include <common>\nvarying float vElev;\nuniform float uInterval;",
        )
        .replace(
          "#include <dithering_fragment>",
          `float _e = vElev / uInterval;
           float _l = 1.0 - smoothstep(0.0, fwidth(_e) * 1.5, abs(fract(_e - 0.5) - 0.5));
           gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.75,0.55,0.27), _l * 0.22);
           #include <dithering_fragment>`,
        );
    };
    return { geometry: geo, material: mat };
  }, []);
  return (
    <mesh
      geometry={geometry}
      material={material}
      receiveShadow
      onPointerMove={(e) => {
        if (reduced) return;
        lantern.current.active = true;
        lantern.current.point.copy((e.object as THREE.Mesh).worldToLocal(e.point.clone()));
      }}
      onPointerOut={() => {
        lantern.current.active = false;
      }}
    />
  );
}

/** Soft warm point light that follows the cursor while it's over the terrain
 *  — a lantern in the dark, not a spotlight, so radius/brightness stay
 *  modest. Position arrives in the terrain's local space (see Terrain's
 *  onPointerMove) so it lines up correctly under the same parallax group. */
function CursorLantern({
  reduced,
  lantern,
}: {
  reduced: boolean;
  lantern: { current: LanternState };
}) {
  const light = useRef<THREE.PointLight>(null);
  const level = useRef(0);
  const target = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    if (!light.current) return;
    if (reduced) {
      light.current.intensity = 0;
      return;
    }
    const want = lantern.current.active ? 1 : 0;
    level.current += (want - level.current) * 0.12;
    light.current.intensity = level.current * 1.1;
    if (level.current > 0.01) {
      target.copy(lantern.current.point);
      target.y += 0.3;
      light.current.position.lerp(target, 0.3);
    }
  });
  return <pointLight ref={light} color="#E8B673" distance={2.4} decay={2} intensity={0} />;
}

function QueryPoint({ reduced, runtime }: { reduced: boolean; runtime: SceneRuntime }) {
  const ref = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const pos = useMemo(() => world(ORIGIN_UV.u, ORIGIN_UV.v, 0.1), []);
  useFrame((state) => {
    const s = sampleFromRuntime(state.clock.elapsedTime, runtime, reduced);
    const sc = (1 + s.queryPulse * 0.15) * (0.9 + s.queryFlash * 0.5);
    if (ref.current) ref.current.scale.setScalar(sc);
    if (haloRef.current) haloRef.current.scale.setScalar(sc * (2.1 + s.queryPulse * 0.5));
    if (mat.current) mat.current.emissiveIntensity = 1.4 + s.queryFlash * 2.4;
  });
  return (
    <group position={pos}>
      <mesh ref={ref}>
        <sphereGeometry args={[0.1, 20, 20]} />
        <meshStandardMaterial ref={mat} color="#C08A45" emissive="#E8B673" emissiveIntensity={1.4} />
      </mesh>
      {/* additive halo — marks the origin as the brightest point on the route */}
      <mesh ref={haloRef}>
        <sphereGeometry args={[0.1, 16, 16]} />
        <meshBasicMaterial
          color="#E8B673"
          transparent
          opacity={0.22}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

// --- Route as individually spaced survey dots -------------------------------
// Previously one thick TubeGeometry with a dash texture, which read as a chain.
// Now: discrete dots, ~1:3 diameter-to-gap, arc-length spaced so they stay
// evenly pitched across steep ground, and slightly fatter near each stop so the
// line reads as plotted-by-hand rather than a mechanical repeat.
const DOT_R = 0.026; // vs. the 0.045 tube radius — the route now defers to the flags
const DOT_SPACING = 0.2; // ground units between dot centres → gap ≈ 3× diameter
const REVEAL_FEATHER = 0.08; // soft width of the drawing front, in segment-t

interface RouteDot {
  pos: THREE.Vector3;
  seg: number;
  /** 0..1 along its own segment. */
  t: number;
  /** 0..1 along the whole route, for the ambient travelling highlight. */
  g: number;
  size: number;
}

function buildRouteDots(): RouteDot[] {
  const stops = [ORIGIN_UV, ...targets];
  const dots: RouteDot[] = [];
  for (let s = 0; s < 3; s++) {
    const a = stops[s];
    const b = stops[s + 1];
    // Leave a little air at each end so dots never sit under the query sphere
    // or the flag pole.
    const tA = s === 0 ? 0.075 : 0.05;
    const tB = 0.95;
    const dense: THREE.Vector3[] = [];
    for (let i = 0; i <= 90; i++) {
      const t = tA + (tB - tA) * (i / 90);
      dense.push(new THREE.Vector3(...world(a.u + (b.u - a.u) * t, a.v + (b.v - a.v) * t, 0.055)));
    }
    const curve = new THREE.CatmullRomCurve3(dense);
    // getSpacedPoints is arc-length parameterised — dots stay evenly pitched on
    // the ground even where the curve climbs, so the reveal front travels at a
    // constant speed instead of surging over the ridges.
    const n = Math.max(4, Math.round(curve.getLength() / DOT_SPACING));
    const pts = curve.getSpacedPoints(n);
    for (let i = 0; i <= n; i++) {
      const t = i / n;
      const nearStop = 1 - THREE.MathUtils.smoothstep(Math.min(t, 1 - t), 0, 0.24);
      const jitter = 0.95 + 0.1 * hash2(s * 31.7 + i * 5.1, i * 2.3);
      dots.push({
        pos: pts[i],
        seg: s,
        t,
        g: (s + t) / 3,
        size: (0.76 + 0.5 * nearStop) * jitter,
      });
    }
  }
  return dots;
}

function SurveyRoute({ reduced, runtime }: { reduced: boolean; runtime: SceneRuntime }) {
  const dots = useMemo(buildRouteDots, []);
  const core = useRef<THREE.InstancedMesh>(null);
  const halo = useRef<THREE.InstancedMesh>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const col = useMemo(() => new THREE.Color(), []);
  const brass = useMemo(() => new THREE.Color("#E8B673"), []);

  useFrame((state) => {
    const c = core.current;
    const h = halo.current;
    if (!c || !h) return;
    const s = sampleFromRuntime(state.clock.elapsedTime, runtime, reduced);

    for (let i = 0; i < dots.length; i++) {
      const d = dots[i];
      // Continuous (not stepped) reveal: each dot fades and swells as the
      // drawing front sweeps past it. No drawRange, no per-frame React state.
      const lit = reduced
        ? 1
        : THREE.MathUtils.smoothstep(s.seg[d.seg], d.t, d.t + REVEAL_FEATHER);
      // Ambient highlight travelling the finished route — either the initial
      // draw-in, or a periodic re-verification pulse.
      let travel = 0;
      if (s.glow >= 0) {
        const dg = Math.abs(d.g - s.glow);
        travel = Math.exp(-(dg * dg) / (2 * 0.06 * 0.06)) * 0.85;
      }
      // Unlit-but-present base state: the route is legible the instant the page
      // paints; only the *lighting* of it animates.
      const scale = d.size * (0.6 + 0.4 * lit + Math.sin(lit * Math.PI) * 0.22);
      const bright = 0.2 + 0.8 * lit + travel * lit;

      dummy.position.copy(d.pos);
      dummy.scale.setScalar(scale);
      dummy.updateMatrix();
      c.setMatrixAt(i, dummy.matrix);
      dummy.scale.setScalar(scale * 2.9);
      dummy.updateMatrix();
      h.setMatrixAt(i, dummy.matrix);

      col.copy(brass).multiplyScalar(bright);
      c.setColorAt(i, col);
      col.copy(brass).multiplyScalar(Math.max(0, lit * 0.5 + travel * 0.8));
      h.setColorAt(i, col);
    }
    c.instanceMatrix.needsUpdate = true;
    h.instanceMatrix.needsUpdate = true;
    if (c.instanceColor) c.instanceColor.needsUpdate = true;
    if (h.instanceColor) h.instanceColor.needsUpdate = true;
  });

  return (
    <>
      <instancedMesh ref={core} args={[undefined, undefined, dots.length]} frustumCulled={false}>
        <sphereGeometry args={[DOT_R, 8, 8]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>
      {/* Restrained "bloom" without a postprocessing pass: one additive halo
          shell per dot. Costs a draw call instead of a full EffectComposer. */}
      <instancedMesh ref={halo} args={[undefined, undefined, dots.length]} frustumCulled={false}>
        <sphereGeometry args={[DOT_R, 8, 8]} />
        <meshBasicMaterial
          transparent
          opacity={0.16}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </instancedMesh>
    </>
  );
}

// --- Fluttering red flag (persists once planted; hover-only filename) -------
const flagVert = /* glsl */ `
  uniform float uTime; varying vec2 vUv;
  void main() {
    vUv = uv;
    vec3 p = position;
    float a = uv.x;
    p.z += sin(uv.x * 6.0 + uTime * 4.0) * 0.06 * a;
    p.y += sin(uv.x * 4.5 + uTime * 3.0) * 0.03 * a;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;
const flagFrag = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vec3 red = vec3(0.757, 0.275, 0.184);
    gl_FragColor = vec4(red * (0.72 + 0.28 * vUv.x), 1.0);
  }
`;

function Flag({
  peak,
  index,
  reduced,
  runtime,
}: {
  peak: Peak;
  index: number;
  reduced: boolean;
  runtime: SceneRuntime;
}) {
  const group = useRef<THREE.Group>(null);
  const pole = useRef<THREE.Mesh>(null);
  const cloth = useRef<THREE.Group>(null);
  const flagMat = useRef<THREE.ShaderMaterial>(null);
  const light = useRef<THREE.PointLight>(null);
  const ringA = useRef<THREE.Mesh>(null);
  const ringB = useRef<THREE.Mesh>(null);
  const summit = useMemo(() => world(peak.u, peak.v, 0), [peak]);
  const poleH = 0.95;
  const clothLow = 0.14; // cloth starts at the foot of the pole…
  const clothHigh = poleH - 0.12; // …and is hoisted to just under the finial
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame((state) => {
    const s = sampleFromRuntime(state.clock.elapsedTime, runtime, reduced);
    // A pulse passing this flag briefly intensifies its glow (s.ring already
    // blends the one-time intro flash with any ambient-pulse flash).
    if (light.current) light.current.intensity = Math.max(s.peak[index], s.ring[index] * 0.7) * 7;
    if (flagMat.current && !reduced) flagMat.current.uniforms.uTime.value = state.clock.elapsedTime;
    const p = s.plant[index];
    if (group.current) group.current.visible = p > 0.001;
    if (pole.current) {
      // The pole grows out of the summit (power3.out) rather than dropping in
      // from off-screen.
      const g = Math.max(0.001, p);
      pole.current.scale.y = g;
      pole.current.position.y = (poleH * g) / 2;
    }
    if (cloth.current) {
      // …then the cloth runs up it with back.out(1.2): a little overshoot past
      // the finial, then settles — the way a flag actually gets planted.
      const h = s.hoist[index];
      cloth.current.position.y = clothLow + (clothHigh - clothLow) * h;
      cloth.current.scale.setScalar(THREE.MathUtils.clamp(h, 0, 1));
      cloth.current.visible = h > 0.001;
    }
    const setRing = (m: THREE.Mesh | null) => {
      if (!m) return;
      const rp = s.ring[index];
      const sc = 0.2 + rp * 1.4;
      m.scale.set(sc, sc, sc);
      (m.material as THREE.MeshBasicMaterial).opacity = rp * 0.8;
    };
    setRing(ringA.current);
    setRing(ringB.current);
  });

  return (
    <group>
      <pointLight ref={light} position={[summit[0], summit[1] + 0.4, summit[2]]} color="#E8B673" intensity={0} distance={4.2} decay={2} />
      {[ringA, ringB].map((r, i) => (
        <mesh key={i} ref={r} position={[summit[0], summit[1] + 0.02, summit[2]]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.24, 0.3, 32]} />
          <meshBasicMaterial color="#C08A45" transparent opacity={0} side={THREE.DoubleSide} toneMapped={false} />
        </mesh>
      ))}
      <group ref={group} position={summit}>
        <mesh ref={pole} position={[0, poleH / 2, 0]} castShadow>
          <cylinderGeometry args={[0.02, 0.02, poleH, 8]} />
          <meshStandardMaterial color="#C08A45" metalness={0.6} roughness={0.35} emissive="#5a3d17" emissiveIntensity={0.4} />
        </mesh>
        <group ref={cloth} position={[0, clothLow, 0]}>
          <mesh position={[0.26, 0, 0]} castShadow>
            <planeGeometry args={[0.5, 0.3, 14, 4]} />
            <shaderMaterial ref={flagMat} vertexShader={flagVert} fragmentShader={flagFrag} uniforms={uniforms} side={THREE.DoubleSide} />
          </mesh>
        </group>
        {/* Elevation reading — always present, low-key mono type. */}
        {peak.elevation !== undefined && (
          <Html position={[-0.02, poleH + 0.06, 0]} center distanceFactor={9} zIndexRange={[4, 0]}>
            <div className="pointer-events-none -translate-x-full whitespace-nowrap pr-1.5 font-mono text-[9px] text-brass/60">
              {peak.elevation.toLocaleString()}m
            </div>
          </Html>
        )}
      </group>
    </group>
  );
}

function Lighting({ reduced, runtime }: { reduced: boolean; runtime: SceneRuntime }) {
  const key = useRef<THREE.DirectionalLight>(null);
  const frozen = useRef(false);
  const lastIntroStart = useRef(runtime.introStart);
  // The only shadow-casters that move are the flags, and they stop moving once
  // the survey resolves. Freezing the shadow map after that removes a 2048²
  // depth pass from every subsequent frame — the biggest per-frame cost in the
  // scene, and the main source of the stutter during the intro. A full
  // redraw-from-scratch (scroll-away-and-back after a while) resets the intro
  // clock, so re-arm the shadow updates when that happens.
  useFrame((state) => {
    if (!key.current) return;
    if (runtime.introStart !== lastIntroStart.current) {
      lastIntroStart.current = runtime.introStart;
      frozen.current = false;
      key.current.shadow.autoUpdate = true;
    }
    if (frozen.current) return;
    const effectiveElapsed = state.clock.elapsedTime - runtime.introStart;
    if (reduced || effectiveElapsed > SURVEY_END + 0.5) {
      key.current.shadow.needsUpdate = true;
      key.current.shadow.autoUpdate = false;
      frozen.current = true;
    }
  });
  return (
    <>
      {/* cool ambient fill so shadows never crush to pure black */}
      <hemisphereLight args={["#334650", "#0B1620", 0.55]} />
      {/* warm key from upper-left, casts soft shadows */}
      <directionalLight
        ref={key}
        position={[-6.5, 8, 4.5]}
        intensity={1.5}
        color="#F2CC8A"
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-near={1}
        shadow-camera-far={26}
        shadow-camera-left={-9}
        shadow-camera-right={9}
        shadow-camera-top={9}
        shadow-camera-bottom={-9}
        shadow-bias={-0.0004}
      />
      {/* cool rim from behind-above to separate the ridge from the background */}
      <directionalLight position={[3, 6, -8]} intensity={0.7} color="#5E7C9A" />
    </>
  );
}

function ParallaxGroup({
  children,
  reduced,
  factor = 0.05,
}: {
  children: React.ReactNode;
  reduced: boolean;
  factor?: number;
}) {
  const group = useRef<THREE.Group>(null);
  const { pointer } = useThree();
  useFrame(() => {
    if (reduced || !group.current) return;
    group.current.rotation.x += (pointer.y * factor - group.current.rotation.x) * 0.05;
    group.current.rotation.y += (pointer.x * factor - group.current.rotation.y) * 0.05;
  });
  return <group ref={group}>{children}</group>;
}

/** Very slow, very small camera oscillation so the scene is never a still. */
function CameraDrift({ reduced }: { reduced: boolean }) {
  const { camera } = useThree();
  const home = useMemo(() => camera.position.clone(), [camera]);
  const look = useMemo(() => new THREE.Vector3(0.2, 0.5, -0.3), []);
  useFrame((state) => {
    if (reduced) return;
    const t = state.clock.elapsedTime;
    camera.position.set(
      home.x + Math.sin(t * 0.11) * 0.16,
      home.y + Math.sin(t * 0.077 + 1.3) * 0.1,
      home.z + Math.cos(t * 0.09) * 0.1,
    );
    camera.lookAt(look);
  });
  return null;
}

/** Linear top-to-bottom alpha fade, used to fake a foreground focal-plane
 *  falloff without a real postprocessing/bokeh pass (none is installed in
 *  this project — see heroTimeline.ts's note on staying dependency-light). */
function buildLinearFadeTexture(): THREE.Texture {
  const w = 8;
  const h = 64;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createLinearGradient(0, h, 0, 0);
  grad.addColorStop(0, "rgba(0,0,0,1)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

/** Approximate foreground depth-of-field: a soft haze over the terrain's
 *  near-left edge (closest to camera), pairing with the Tier-1 atmospheric
 *  depth gradient so both read as one focal-falloff system rather than two.
 *  Not true lens blur — that would need a bokeh/postprocessing pass, which
 *  isn't worth the new dependency for this one effect. */
function ForegroundHaze() {
  const texture = useMemo(buildLinearFadeTexture, []);
  return (
    <mesh position={[-2.5, 0.42, 3.9]} rotation={[-Math.PI / 2.5, 0, 0.3]}>
      <planeGeometry args={[4.4, 2.2]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={0.2}
        color="#0F1A24"
        depthWrite={false}
        toneMapped={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

/** Sparse dust catching the key light above the ridge. One draw call. */
function DustMotes({ reduced }: { reduced: boolean }) {
  const ref = useRef<THREE.Points>(null);
  const geometry = useMemo(() => {
    const n = 70;
    const arr = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const p = targets[i % targets.length];
      const w = world(p.u, p.v, 0);
      arr[i * 3] = w[0] + (hash2(i * 1.7, 3.1) - 0.5) * 4.5;
      arr[i * 3 + 1] = w[1] + hash2(i * 2.9, 8.4) * 1.9;
      arr[i * 3 + 2] = w[2] + (hash2(i * 4.3, 1.9) - 0.5) * 4.5;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
    return g;
  }, []);
  useFrame((state) => {
    if (reduced || !ref.current) return;
    const t = state.clock.elapsedTime;
    ref.current.position.y = Math.sin(t * 0.13) * 0.12;
    ref.current.rotation.y = t * 0.008;
  });
  return (
    <points ref={ref} geometry={geometry}>
      <pointsMaterial
        size={0.035}
        color="#E8B673"
        transparent
        opacity={0.3}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
        toneMapped={false}
      />
    </points>
  );
}

// --- Background enrichment: depth and atmosphere, none of it competing with
// the route/flags for attention. Cool navy/verdigris register only — brass
// stays the one warm colour in the scene, reserved for the route/flags/flare.

/** A jagged horizon silhouette as a single triangle-strip mesh — cheap depth
 *  layering without a second full terrain mesh. */
function buildRidgeGeometry(seed: number, width: number, baseY: number, amp: number, segs: number) {
  const positions: number[] = [];
  const bottomY = baseY - 3;
  for (let i = 0; i <= segs; i++) {
    const u = i / segs;
    const x = (u - 0.5) * width;
    const y = baseY + amp * fbm(u * 2.1 + seed, seed * 2.7);
    positions.push(x, bottomY, 0, x, y, 0);
  }
  const idx: number[] = [];
  for (let i = 0; i < segs; i++) {
    const a = i * 2;
    const b = i * 2 + 1;
    const c = (i + 1) * 2;
    const d = (i + 1) * 2 + 1;
    idx.push(a, b, c, b, d, c);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geo.setIndex(idx);
  return geo;
}
function RidgeLayer({
  z,
  y,
  amp,
  width,
  color,
  seed,
}: {
  z: number;
  y: number;
  amp: number;
  width: number;
  color: string;
  seed: number;
}) {
  const geometry = useMemo(() => buildRidgeGeometry(seed, width, y, amp, 40), [seed, width, y, amp]);
  return (
    <mesh geometry={geometry} position={[0, 0, z]}>
      <meshBasicMaterial color={color} fog toneMapped={false} side={THREE.DoubleSide} />
    </mesh>
  );
}
/** Two much flatter, darker silhouettes behind the main terrain — "the atlas
 *  extends beyond what's mapped yet." Wrapped in its own, slower parallax. */
function RidgelineSilhouettes({ reduced }: { reduced: boolean }) {
  return (
    <ParallaxGroup reduced={reduced} factor={0.018}>
      <RidgeLayer z={-9} y={1.25} amp={0.75} width={34} color="#0A121B" seed={4.1} />
      <RidgeLayer z={-15} y={1.85} amp={1.1} width={48} color="#070C12" seed={11.7} />
    </ParallaxGroup>
  );
}

/** Faint lat/long grid behind the terrain — reinforces the "chart" framing at
 *  a barely-there ~4-6% opacity. */
function buildGraticuleGeometry() {
  const halfW = 20;
  const halfH = 9;
  const step = 1.8;
  const lines: number[] = [];
  for (let x = -halfW; x <= halfW + 0.001; x += step) {
    lines.push(x, -halfH, 0, x, halfH, 0);
  }
  for (let y = -halfH; y <= halfH + 0.001; y += step) {
    lines.push(-halfW, y, 0, halfW, y, 0);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.Float32BufferAttribute(lines, 3));
  return geo;
}
function Graticule({ reduced }: { reduced: boolean }) {
  const geometry = useMemo(buildGraticuleGeometry, []);
  const mat = useRef<THREE.LineBasicMaterial>(null);
  useFrame((state) => {
    if (reduced || !mat.current) return;
    // Idle shimmer, not movement: opacity only, well under the range that
    // would read as flicker.
    mat.current.opacity = 0.06 + Math.sin(state.clock.elapsedTime * 0.22) * 0.018;
  });
  return (
    // Deliberately not `fog`-affected — at this depth the exp2 fog would
    // crush the already-low opacity to nothing, defeating the "barely
    // visible" effect rather than achieving it.
    <lineSegments geometry={geometry} position={[0, 3, -8]}>
      <lineBasicMaterial ref={mat} color="#C08A45" transparent opacity={0.06} toneMapped={false} />
    </lineSegments>
  );
}

/** Thin drifting mist planes at the terrain's base — softens the silhouette
 *  edge against the background. */
function GroundMist({ reduced }: { reduced: boolean }) {
  const a = useRef<THREE.Mesh>(null);
  const b = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (reduced) return;
    const t = state.clock.elapsedTime;
    if (a.current) a.current.position.x = Math.sin(t * 0.05) * 0.6;
    if (b.current) b.current.position.x = Math.sin(t * 0.045 + 2.1) * 0.7;
  });
  return (
    <>
      <mesh ref={a} position={[0, -1.05, -1.2]} rotation={[-Math.PI / 2.4, 0, 0]}>
        <planeGeometry args={[9, 3]} />
        <meshBasicMaterial color="#4A6270" transparent opacity={0.07} depthWrite={false} fog toneMapped={false} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={b} position={[0, -1.15, 0.1]} rotation={[-Math.PI / 2.4, 0, 0]}>
        <planeGeometry args={[9, 3]} />
        <meshBasicMaterial color="#4A6270" transparent opacity={0.05} depthWrite={false} fog toneMapped={false} side={THREE.DoubleSide} />
      </mesh>
    </>
  );
}

/** Soft radial-falloff alpha texture, built once on a canvas — used as the
 *  drifting cloud shadow's opacity mask so it reads as a diffuse patch rather
 *  than a hard-edged disc. */
function buildSoftCircleTexture(): THREE.Texture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, "rgba(0,0,0,1)");
  grad.addColorStop(0.6, "rgba(0,0,0,0.5)");
  grad.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  const tex = new THREE.CanvasTexture(canvas);
  tex.needsUpdate = true;
  return tex;
}

/** A large, very soft, low-opacity shadow patch slowly drifting across the
 *  terrain — independent of the ~22-32s pulse cycle so the two never read as
 *  synchronised. The cheapest way to make flat-shaded terrain read as a lit
 *  landscape under moving sky rather than a static render. */
function CloudShadow({ reduced }: { reduced: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  const texture = useMemo(buildSoftCircleTexture, []);
  useFrame((state) => {
    if (reduced || !ref.current) return;
    const t = state.clock.elapsedTime;
    ref.current.position.x = Math.sin(t * (2 * Math.PI) / 26) * 3.2;
    ref.current.position.z = Math.cos(t * (2 * Math.PI) / 34 + 1.1) * 2.4 - 0.5;
  });
  return (
    <mesh ref={ref} position={[0, 1.15, -0.5]} rotation={[-Math.PI / 2, 0, 0]}>
      <planeGeometry args={[5.5, 5.5]} />
      <meshBasicMaterial
        map={texture}
        transparent
        opacity={0.16}
        color="#0B1620"
        depthWrite={false}
        toneMapped={false}
      />
    </mesh>
  );
}

const starVert = /* glsl */ `
  attribute float aPhase;
  uniform float uTime;
  uniform float uTwinkle;
  varying float vAlpha;
  void main() {
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = 5.5 * (24.0 / -mvPosition.z);
    gl_Position = projectionMatrix * mvPosition;
    float wave = 0.5 + 0.5 * sin(uTime * (0.5 + aPhase * 0.35) + aPhase * 6.2831);
    vAlpha = mix(1.0, 0.35 + 0.65 * wave, uTwinkle);
  }
`;
const starFrag = /* glsl */ `
  uniform vec3 uColor;
  uniform float uOpacity;
  varying float vAlpha;
  void main() {
    float d = length(gl_PointCoord - vec2(0.5));
    if (d > 0.5) discard;
    float falloff = 1.0 - smoothstep(0.0, 0.5, d);
    gl_FragColor = vec4(uColor, uOpacity * vAlpha * falloff);
  }
`;

/** Sparse, dim points high in the background — a faint sextant-navigation
 *  field, drifting independently and very slowly, each star twinkling on its
 *  own staggered phase (reduced-motion: static, no twinkle). */
function CelestialField({ reduced }: { reduced: boolean }) {
  const ref = useRef<THREE.Points>(null);
  const mat = useRef<THREE.ShaderMaterial>(null);
  const { geometry, uniforms } = useMemo(() => {
    const n = 90;
    const pos = new Float32Array(n * 3);
    const phase = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const a = hash2(i * 3.3, 7.1) * Math.PI * 2;
      const r = 14 + hash2(i * 5.7, 2.2) * 10;
      pos[i * 3] = Math.cos(a) * r;
      pos[i * 3 + 1] = 4 + hash2(i * 1.9, 9.4) * 6;
      pos[i * 3 + 2] = -8 - hash2(i * 8.1, 4.6) * 14;
      phase[i] = hash2(i * 6.1, 4.9);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aPhase", new THREE.BufferAttribute(phase, 1));
    return {
      geometry: g,
      uniforms: {
        uTime: { value: 0 },
        uTwinkle: { value: reduced ? 0 : 1 },
        uColor: { value: new THREE.Color("#8FA6B8") },
        uOpacity: { value: 0.35 },
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useFrame((state) => {
    if (mat.current) mat.current.uniforms.uTime.value = state.clock.elapsedTime;
    if (reduced || !ref.current) return;
    ref.current.rotation.y = state.clock.elapsedTime * 0.003;
  });
  return (
    <points ref={ref} geometry={geometry}>
      <shaderMaterial
        ref={mat}
        vertexShader={starVert}
        fragmentShader={starFrag}
        uniforms={uniforms}
        transparent
        depthWrite={false}
        toneMapped={false}
      />
    </points>
  );
}

/** A rare brass streak crossing the upper background — a distant signal
 *  flare, not a repeating element (every 60-120s, ~0.7s to cross and fade).
 *  Scheduled by TimelineDriver on `runtime`. */
function SurveyFlare({ reduced, runtime }: { reduced: boolean; runtime: SceneRuntime }) {
  const ref = useRef<THREE.Mesh>(null);
  const mat = useRef<THREE.MeshBasicMaterial>(null);
  useFrame((state) => {
    if (!ref.current || !mat.current) return;
    if (reduced || runtime.tabHidden || runtime.flareStart === null) {
      ref.current.visible = false;
      return;
    }
    const p = clamp01((state.clock.elapsedTime - runtime.flareStart) / FLARE_DURATION);
    ref.current.visible = true;
    const appear = Math.min(1, p * 6);
    const fade = 1 - Math.pow(p, 2.2);
    ref.current.position.set(-9 + p * 20, 7 - p * 2.6, -11);
    mat.current.opacity = Math.min(appear, fade) * 0.5;
  });
  return (
    <mesh ref={ref} rotation={[0, 0, -0.5]} visible={false}>
      <planeGeometry args={[1.3, 0.025]} />
      <meshBasicMaterial
        ref={mat}
        color="#E8B673"
        transparent
        opacity={0}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </mesh>
  );
}

function Scene({ reduced, runtime }: { reduced: boolean; runtime: SceneRuntime }) {
  const lantern = useRef<LanternState>({ active: false, point: new THREE.Vector3() });
  return (
    <>
      <fogExp2 attach="fog" args={["#0F1A24", 0.058]} />
      <TimelineDriver runtime={runtime} reduced={reduced} />
      <Lighting reduced={reduced} runtime={runtime} />
      <CameraDrift reduced={reduced} />
      <CelestialField reduced={reduced} />
      <RidgelineSilhouettes reduced={reduced} />
      <Graticule reduced={reduced} />
      <GroundMist reduced={reduced} />
      <SurveyFlare reduced={reduced} runtime={runtime} />
      <ParallaxGroup reduced={reduced}>
        <group position={[0, -0.6, 0]}>
          <Terrain reduced={reduced} lantern={lantern} />
          <CursorLantern reduced={reduced} lantern={lantern} />
          <QueryPoint reduced={reduced} runtime={runtime} />
          <SurveyRoute reduced={reduced} runtime={runtime} />
          {targets.map((p, i) => (
            <Flag key={i} peak={p} index={i} reduced={reduced} runtime={runtime} />
          ))}
          <DustMotes reduced={reduced} />
          <CloudShadow reduced={reduced} />
          <ForegroundHaze />
        </group>
      </ParallaxGroup>
    </>
  );
}

// --- 2D fallback (mobile / low-power / no-WebGL): resolved state, flags only --
function SurveyFallback() {
  const proj = (u: number, v: number) => ({ x: 40 + u * 340, y: 220 - heightAt(u, v) * 150 });
  const o = proj(ORIGIN_UV.u, ORIGIN_UV.v);
  const pts = targets.map((p) => proj(p.u, p.v));
  return (
    <svg viewBox="0 0 420 260" className="h-full w-full" role="img" aria-label="Survey route across documents">
      <polyline
        points={[o, ...pts].map((p) => `${p.x},${p.y}`).join(" ")}
        fill="none"
        stroke="#E0A24A"
        strokeWidth={1.6}
        strokeDasharray="4 4"
        strokeLinecap="round"
      />
      <circle cx={o.x} cy={o.y} r={4} fill="#C08A45" />
      {pts.map((p, i) => (
        <g key={i}>
          <line x1={p.x} y1={p.y} x2={p.x} y2={p.y - 22} stroke="#C08A45" strokeWidth={1.4} />
          <path d={`M${p.x} ${p.y - 22} l14 5 l-14 5 z`} fill="#C1462F" />
        </g>
      ))}
    </svg>
  );
}

/** First-paint load transition: a few organic ink-bleed blots spread across
 *  the dark void and merge, revealing the terrain underneath rather than a
 *  plain fade — "the map being drawn as the visitor arrives". Pure CSS, one
 *  shot, `animation-fill-mode: both` so it needs no JS scheduling or cleanup;
 *  the global reduced-motion rule in globals.css zeroes its duration, and the
 *  fully-revealed end state is what's left when that happens. Works for both
 *  the WebGL scene and the 2D fallback since it's a sibling overlay, not part
 *  of either. */
function InkBleedIntro() {
  return (
    <div className="ink-bleed pointer-events-none absolute inset-0 z-10" aria-hidden>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full">
        <defs>
          <filter id="ink-bleed-rough" x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence type="fractalNoise" baseFrequency="0.014 0.02" numOctaves={2} seed={7} result="noise" />
            <feDisplacementMap in="SourceGraphic" in2="noise" scale={16} />
          </filter>
          <mask id="ink-bleed-mask" maskContentUnits="userSpaceOnUse">
            <rect x="0" y="0" width="100" height="100" fill="white" />
            <g filter="url(#ink-bleed-rough)">
              <circle className="ink-blot" style={{ animationDelay: "0s" }} cx="22" cy="72" r="0" fill="black" />
              <circle className="ink-blot" style={{ animationDelay: "0.12s" }} cx="52" cy="42" r="0" fill="black" />
              <circle className="ink-blot" style={{ animationDelay: "0.24s" }} cx="76" cy="55" r="0" fill="black" />
            </g>
          </mask>
        </defs>
        <rect x="0" y="0" width="100" height="100" fill="#0F1A24" mask="url(#ink-bleed-mask)" />
      </svg>
    </div>
  );
}

export function HeroSurveyScene() {
  const { reducedMotion, lowPower, webgl } = useCapabilities();
  const [narrow, setNarrow] = useState(false);
  const [visible, setVisible] = useState(true);
  const hostRef = useRef<HTMLDivElement>(null);
  const runtimeRef = useRef<SceneRuntime>(createRuntime());

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 900px)");
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);

  useEffect(() => {
    const onVisibility = () => {
      runtimeRef.current.tabHidden = document.visibilityState === "hidden";
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  useEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    // Full redraw-from-scratch is reserved for scroll-into-view after the
    // hero has been out of view for a while — not a fixed short timer.
    let hiddenAtWall: number | null = null;
    const io = new IntersectionObserver(
      ([entry]) => {
        const isVisible = entry.isIntersecting;
        if (!isVisible) {
          hiddenAtWall = Date.now();
        } else if (hiddenAtWall !== null) {
          if (Date.now() - hiddenAtWall > AWAY_RESET_MS) {
            runtimeRef.current.resetRequested = true;
          }
          hiddenAtWall = null;
        }
        setVisible(isVisible);
      },
      { threshold: 0.05 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const useFallback = narrow || lowPower || !webgl;

  return (
    <div ref={hostRef} className="relative h-full w-full">
      {useFallback ? (
        <div className="flex h-full items-center justify-center p-4">
          <SurveyFallback />
        </div>
      ) : (
        <Canvas
          className="h-full w-full"
          shadows="soft"
          gl={{ alpha: true, antialias: true, powerPreference: "high-performance", toneMappingExposure: 1.25 }}
          dpr={[1, 2]}
          frameloop={visible ? "always" : "never"}
          camera={{ position: [0, 6.2, 10.2], fov: 40 }}
          onCreated={({ camera }) => camera.lookAt(0.2, 0.5, -0.3)}
        >
          <Scene reduced={reducedMotion} runtime={runtimeRef.current} />
        </Canvas>
      )}
      <InkBleedIntro />
    </div>
  );
}
