"use client";

import dynamic from "next/dynamic";

// WebGL must not run on the server; load the scene client-side only.
const LivingAtlas = dynamic(() => import("./LivingAtlas"), { ssr: false });

/**
 * Full-bleed ambient backdrop for the landing page. Non-interactive: the atlas
 * drifts behind the cartouche without capturing pointer events.
 */
export default function AtlasBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      <LivingAtlas />
    </div>
  );
}
