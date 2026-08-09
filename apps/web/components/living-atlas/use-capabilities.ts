"use client";

import { useEffect, useState } from "react";

import { motionDisabled, subscribeMotion } from "@/lib/motion";

/**
 * Tracks `prefers-reduced-motion` OR the user's explicit "freeze motion"
 * preference (set in Settings). When true, the atlas holds still instead of
 * rotating — motion earns meaning by scarcity.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const compute = () => setReduced(mq.matches || motionDisabled());
    compute();
    mq.addEventListener("change", compute);
    const unsub = subscribeMotion(compute);
    return () => {
      mq.removeEventListener("change", compute);
      unsub();
    };
  }, []);
  return reduced;
}

function detectLowPower(): boolean {
  if (typeof navigator === "undefined") return false;
  const cores = navigator.hardwareConcurrency ?? 8;
  // deviceMemory is non-standard but widely available in Chromium.
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 8;
  return cores <= 4 || memory <= 4;
}

function detectWebGL(): boolean {
  if (typeof document === "undefined") return true;
  try {
    const canvas = document.createElement("canvas");
    return !!(
      canvas.getContext("webgl2") ||
      canvas.getContext("webgl") ||
      canvas.getContext("experimental-webgl")
    );
  } catch {
    return false;
  }
}

export interface Capabilities {
  reducedMotion: boolean;
  lowPower: boolean;
  webgl: boolean;
  /**
   * Functional mode should fall back to the 2D view when true (reduced motion,
   * a low-power device, or no WebGL at all). The citations panel always works.
   */
  functionalDegraded: boolean;
}

/**
 * Resolves rendering capabilities on the client. Everything starts "capable"
 * during SSR/first paint to avoid hydration mismatch, then updates after mount.
 */
export function useCapabilities(): Capabilities {
  const reducedMotion = useReducedMotion();
  const [lowPower, setLowPower] = useState(false);
  const [webgl, setWebgl] = useState(true);

  useEffect(() => {
    setLowPower(detectLowPower());
    setWebgl(detectWebGL());
  }, []);

  return {
    reducedMotion,
    lowPower,
    webgl,
    functionalDegraded: reducedMotion || lowPower || !webgl,
  };
}
