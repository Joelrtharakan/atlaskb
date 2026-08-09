// The Survey-Route hero timeline. In-house substitute for a GSAP timeline
// (kept dependency-free deliberately — see NOTE below): labeled beats in one
// place.
//
// Two-tier cadence:
//  - INTRO: plays once, fast (~1.6s) — first paint should show a fully
//    resolved route almost immediately, not make a first-time visitor sit
//    through a multi-second draw.
//  - AMBIENT PULSE: after the intro settles, a single travelling glow re-runs
//    the already-drawn route every ~22–32s (randomized, scheduled externally —
//    see HeroSurveyScene's TimelineDriver). This function only *renders* a
//    pulse given how far into it we are; it does not schedule pulses itself.
//
// NOTE ON EASING: the curves below are the exact GSAP curves, reimplemented.
// `power2InOut` === GSAP "power2.inOut", `power3Out` === "power3.out",
// `backOut(t, 1.2)` === "back.out(1.2)". Every consumer samples the timeline
// from inside R3F's `useFrame` via refs — no React state is touched per frame,
// so nothing here can trigger a re-render.

const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

/** GSAP "power2.inOut" — deliberate, hand-plotted acceleration + settle. */
export const power2InOut = (t: number) =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
/** GSAP "power3.out" — quick departure, long graceful arrival. */
export const power3Out = (t: number) => 1 - Math.pow(1 - t, 3);
/** GSAP "power2.out". */
export const power2Out = (t: number) => 1 - Math.pow(1 - t, 2);
/** GSAP "back.out(n)" — overshoot past the target, then settle back onto it. */
export const backOut = (t: number, n = 1.2) => {
  const p = t - 1;
  return p * p * ((n + 1) * p + n) + 1;
};

/** Progress 0..1 across [start,start+dur], clamped, STAYS 1 after. */
const spanRaw = (t: number, start: number, dur: number) => clamp01((t - start) / dur);
const hump = (t: number, start: number, dur: number) => {
  const p = (t - start) / dur;
  return p > 0 && p < 1 ? Math.sin(p * Math.PI) : 0;
};

export interface TimelineState {
  queryPulse: number;
  queryFlash: number;
  /** Route-draw progress per segment, power2.inOut-eased. */
  seg: [number, number, number];
  peak: [number, number, number];
  /** Pole rising out of the summit, power3.out-eased. */
  plant: [number, number, number];
  /** Cloth running up the pole, back.out(1.2) — overshoot and settle. */
  hoist: [number, number, number];
  ring: [number, number, number];
  /** Ambient highlight travelling along the drawn route, 0..1, or -1 = none active. */
  glow: number;
  /** Wall-clock seconds since scene start (for flutter/drift phases). */
  t: number;
}

// Short settle-in — the whole intro resolves in well under two seconds.
const SEG = [0.05, 0.4, 0.75];
const SEG_DUR = 0.32;
const PEAK = [0.28, 0.63, 0.98];
const PEAK_DUR = 0.22;
const PLANT = [0.33, 0.68, 1.03];
const PLANT_DUR = 0.28;
const HOIST = [0.4, 0.75, 1.1];
const HOIST_DUR = 0.32;
const RING = [0.48, 0.83, 1.18];
const RING_DUR = 0.32;
/** Everything is resolved by here — used to freeze the shadow map and to gate
 *  pulse scheduling (no ambient pulse until the intro is fully settled). */
export const SURVEY_END = 1.55;

// Ambient pulse-replay tuning. Scheduling (the randomized 22–32s interval,
// tab-visibility pause, and the >60s-away full-redraw rule) lives in
// HeroSurveyScene's TimelineDriver — this module only renders a pulse given
// "seconds since it started".
export const PULSE_DURATION = 2.6;
export const PULSE_MIN_INTERVAL = 22;
export const PULSE_MAX_INTERVAL = 32;
/** Roughly where each flag sits along the 0..1 route parameterisation used by
 *  SurveyRoute's dot `g` values (flags are approximately at the end of each
 *  of the 3 segments). Only needs to be "roughly" — it drives a brief flash,
 *  not a hard sync point. */
const PULSE_FLAG_G = [1 / 3, 2 / 3, 1];
const PULSE_FLASH_WIDTH = 0.05;

export function randomPulseInterval(): number {
  return PULSE_MIN_INTERVAL + Math.random() * (PULSE_MAX_INTERVAL - PULSE_MIN_INTERVAL);
}

const END: TimelineState = {
  queryPulse: 1,
  queryFlash: 0,
  seg: [1, 1, 1],
  peak: [1, 1, 1],
  plant: [1, 1, 1],
  hoist: [1, 1, 1],
  ring: [0, 0, 0],
  glow: -1,
  t: 0,
};

/**
 * @param elapsed seconds since the current intro started (resets to 0 on
 *   mount and on a full redraw-from-scratch).
 * @param reducedMotion resolved end-state, no motion, no pulsing.
 * @param pulseElapsed seconds since the active ambient pulse started, or -1
 *   if no pulse is currently running (scheduling lives in the caller).
 */
export function sampleTimeline(
  elapsed: number,
  reducedMotion: boolean,
  pulseElapsed = -1,
): TimelineState {
  if (reducedMotion) return END;

  const t = elapsed;
  const queryPulse = 0.5 + 0.5 * Math.sin((t / 1.6) * Math.PI * 2);
  const queryFlash = t > 0.1 && t < 0.42 ? Math.sin(((t - 0.1) / 0.32) * Math.PI) : 0;

  const seg = SEG.map((s) => power2InOut(spanRaw(t, s, SEG_DUR))) as [number, number, number];
  const peak = PEAK.map((s) => power2Out(spanRaw(t, s, PEAK_DUR))) as [number, number, number];
  const plant = PLANT.map((s) => power3Out(spanRaw(t, s, PLANT_DUR))) as [number, number, number];
  const hoist = HOIST.map((s) => backOut(spanRaw(t, s, HOIST_DUR), 1.2)) as [
    number,
    number,
    number,
  ];
  const introRing = RING.map((s) => hump(t, s, RING_DUR)) as [number, number, number];

  let glow = -1;
  const pulseRing: [number, number, number] = [0, 0, 0];
  if (pulseElapsed >= 0 && pulseElapsed <= PULSE_DURATION) {
    const p = clamp01(pulseElapsed / PULSE_DURATION);
    glow = power2InOut(p);
    for (let i = 0; i < 3; i++) {
      const d = glow - PULSE_FLAG_G[i];
      pulseRing[i] = Math.exp(-(d * d) / (2 * PULSE_FLASH_WIDTH * PULSE_FLASH_WIDTH));
    }
  }
  const ring = [
    Math.max(introRing[0], pulseRing[0]),
    Math.max(introRing[1], pulseRing[1]),
    Math.max(introRing[2], pulseRing[2]),
  ] as [number, number, number];

  return { queryPulse, queryFlash, seg, peak, plant, hoist, ring, glow, t };
}
