"use client";

import dynamic from "next/dynamic";

import { useCapabilities } from "./use-capabilities";

// WebGL must not run on the server; load the scene client-side only. This also
// keeps the Three.js bundle out of the initial payload for pages that don't use
// the atlas.
const LivingAtlas = dynamic(() => import("./LivingAtlas"), { ssr: false });

/**
 * Full-bleed ambient backdrop for the landing page. Non-interactive: the atlas
 * drifts behind the cartouche without capturing pointer events. Respects
 * reduced motion (freezes to a composed frame) and skips rendering entirely
 * where WebGL is unavailable.
 */
export default function AtlasBackdrop() {
  const { reducedMotion, webgl } = useCapabilities();
  if (!webgl) return null;
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      {/* Shift the field to the right so the left-margin cartouche sits on clean paper. */}
      <LivingAtlas mode="ambient" reducedMotion={reducedMotion} offsetX={3.4} />
    </div>
  );
}
