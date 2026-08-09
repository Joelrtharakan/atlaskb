"use client";

import { Canvas, type CanvasProps } from "@react-three/fiber";
import { type ReactNode } from "react";

import { useCapabilities } from "../living-atlas/use-capabilities";

export interface AtlasCanvasProps extends Partial<CanvasProps> {
  /** Scene content. Provide this OR `render` (which also gives you reducedMotion). */
  children?: ReactNode;
  /**
   * 2D/CSS equivalent shown instead of the scene when the device can't (or
   * shouldn't) run it: no WebGL, or a low-power device. This enforces the
   * cross-cutting rule that a laggy scene is never forced — every treatment
   * passes a well-composed static fallback here.
   */
  fallback?: ReactNode;
  /**
   * Reduced-motion is NOT a reason to drop to the fallback — the scene still
   * renders, but each primitive freezes to a composed frame. We forward the
   * flag so children can honor it; the value comes from useCapabilities.
   */
  render?: (caps: { reducedMotion: boolean }) => ReactNode;
  className?: string;
}

/**
 * Shared wrapper for every atlas-world scene. Centralizes the degradation rules
 * so no per-page treatment has to re-implement them:
 *   - no WebGL / low-power  → render `fallback` (2D), never a broken/laggy canvas
 *   - prefers-reduced-motion → scene renders but frozen (passed to children)
 *   - the surrounding page's data/UI is always usable; this only owns its box
 *
 * Pages lazy-load the component that renders this via `dynamic(..., {ssr:false})`
 * so the Three.js bundle is per-route and a no-3D page pays nothing.
 */
export function AtlasCanvas({
  children,
  fallback = null,
  render,
  className = "h-full w-full",
  camera = { position: [0, 0, 12], fov: 45 },
  ...rest
}: AtlasCanvasProps) {
  const { webgl, lowPower, reducedMotion } = useCapabilities();

  if (!webgl || lowPower) return <>{fallback}</>;

  return (
    <Canvas
      className={className}
      camera={camera}
      gl={{ alpha: true, antialias: true, powerPreference: "high-performance" }}
      dpr={[1, 1.75]}
      {...rest}
    >
      {render ? render({ reducedMotion }) : children}
    </Canvas>
  );
}
